"""Build a Yahoo-compatible IEF-like intermediate-term U.S. Treasury dataset."""

from __future__ import annotations

import argparse
import csv
import hashlib
import io
import json
import math
from datetime import date, datetime, time, timedelta, timezone
from pathlib import Path
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

import requests


ASSET_ID = "intermediate_term_us_treasury"
ASSET_NAME = "Intermediate-Term U.S. Treasury / IEF-like Total Return"
START_DATE = date(1970, 1, 1)
FED_NOMINAL_YIELD_CURVE_URL = "https://www.federalreserve.gov/data/yield-curve-tables/feds200628.csv"
# 8.5-year maturity approximates the midpoint of the IEF 7-10 year target maturity band.
SYNTHETIC_MATURITY_YEARS = 8.5
VFITX_SYMBOL = "VFITX"
IEF_SYMBOL = "IEF"
SOURCE = "Federal Reserve nominal yield curve; Yahoo Finance chart API (VFITX and IEF adjusted close)"
YAHOO_COLUMNS = ["Date", "Open", "High", "Low", "Close", "Adj Close", "Volume"]
PROJECT_COLUMNS = ["Price Return", "Total Return", "Source", "Quality Flag", "Source Notes"]
OUTPUT_COLUMNS = YAHOO_COLUMNS + PROJECT_COLUMNS
FED_SYNTHETIC_FLAG = "model_fed_yield_curve_8pt5y_par_treasury_total_return"
VFITX_FLAG = "observed_yahoo_vfitx_intermediate_treasury_total_return_proxy"
IEF_FLAG = "observed_yahoo_ief_7_10_treasury_total_return"
FED_SYNTHETIC_NOTES = (
    "Synthetic 8.5-year constant-maturity par Treasury model using Federal Reserve nominal zero curves. "
    "Adj Close includes coupon carry; this is model-derived, not an observed fund or constituent-level index."
)
VFITX_NOTES = (
    "Normalized index. Close compounds VFITX close returns; Adj Close compounds VFITX adjusted-close returns. "
    "Used as an intermediate-term Treasury fund proxy before IEF has daily return history."
)
IEF_NOTES = (
    "Normalized index. Close compounds IEF close returns; Adj Close compounds IEF adjusted-close returns. "
    "Used for IEF-like 7-10 year Treasury exposure after IEF daily return history begins."
)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--end-date", default=date.today().isoformat(), help="Inclusive end date, YYYY-MM-DD.")
    parser.add_argument("--root", default=".", help="Project root.")
    return parser.parse_args()


def unix_seconds(day: date) -> int:
    return int(datetime.combine(day, time.min, tzinfo=timezone.utc).timestamp())


def fetch_chart(symbol: str, end_date: date, start_date: date = START_DATE) -> dict:
    period1 = unix_seconds(start_date)
    period2 = unix_seconds(end_date + timedelta(days=1))
    url = (
        f"https://query1.finance.yahoo.com/v8/finance/chart/{symbol}"
        f"?period1={period1}&period2={period2}&interval=1d&events=history&includeAdjustedClose=true"
    )
    response = requests.get(url, timeout=60, headers={"User-Agent": "Mozilla/5.0"})
    response.raise_for_status()
    payload = response.json()
    error = payload.get("chart", {}).get("error")
    if error:
        raise RuntimeError(f"Yahoo chart error for {symbol}: {error}")
    return payload


def fetch_fed_nominal_yield_curve() -> str:
    response = requests.get(FED_NOMINAL_YIELD_CURVE_URL, timeout=90, headers={"User-Agent": "Mozilla/5.0"})
    response.raise_for_status()
    return response.text


def parse_fed_yield_curve_csv(text: str, end_date: date) -> list[dict[str, float | str]]:
    lines = text.splitlines()
    header_index = next(index for index, line in enumerate(lines) if line.startswith("Date,"))
    reader = csv.DictReader(io.StringIO("\n".join(lines[header_index:])))
    rows: list[dict[str, float | str]] = []
    for row in reader:
        row_date = date.fromisoformat(row["Date"])
        if row_date < START_DATE or row_date > end_date:
            continue
        parsed: dict[str, float | str] = {"Date": row_date.isoformat()}
        for key in ["BETA0", "BETA1", "BETA2", "BETA3", "TAU1", "TAU2"]:
            if row.get(key) and row[key] != "NA":
                parsed[key] = float(row[key])
        for maturity in range(1, 31):
            key = f"SVENY{maturity:02d}"
            if row.get(key) and row[key] != "NA":
                parsed[key] = float(row[key]) / 100.0
        if "BETA0" in parsed and "TAU1" in parsed:
            rows.append(parsed)
    return rows


def chart_rows(payload: dict) -> list[dict[str, float | int | str]]:
    result = payload["chart"]["result"][0]
    timestamps = result.get("timestamp") or []
    quote = result["indicators"]["quote"][0]
    adjclose = result.get("indicators", {}).get("adjclose", [{}])[0].get("adjclose", [])
    meta = result.get("meta", {})
    timezone_name = meta.get("exchangeTimezoneName", "America/New_York")
    try:
        exchange_tz = ZoneInfo(timezone_name)
    except ZoneInfoNotFoundError:
        exchange_tz = timezone(timedelta(seconds=int(meta.get("gmtoffset", 0))))

    rows: list[dict[str, float | int | str]] = []
    for index, timestamp in enumerate(timestamps):
        close = quote.get("close", [None])[index]
        adjusted = adjclose[index] if index < len(adjclose) else close
        if close is None or adjusted is None:
            continue
        rows.append(
            {
                "Date": datetime.fromtimestamp(timestamp, exchange_tz).date().isoformat(),
                "Close": float(close),
                "Adj Close": float(adjusted),
                "Volume": quote.get("volume", [None])[index],
            }
        )
    return rows


def round_float(value: float | None) -> str:
    if value is None:
        return ""
    return f"{float(value):.10f}".rstrip("0").rstrip(".")


def interpolated_zero_rate(curve: dict[str, float | str], maturity: float) -> float:
    if f"SVENY{int(round(maturity)):02d}" not in curve:
        return fitted_zero_rate(curve, maturity)
    if maturity <= 1:
        return float(curve["SVENY01"]) if "SVENY01" in curve else fitted_zero_rate(curve, maturity)
    if maturity >= 30:
        return float(curve["SVENY30"]) if "SVENY30" in curve else fitted_zero_rate(curve, maturity)
    lower = math.floor(maturity)
    upper = math.ceil(maturity)
    lower_key = f"SVENY{lower:02d}"
    upper_key = f"SVENY{upper:02d}"
    if lower_key not in curve or upper_key not in curve:
        return fitted_zero_rate(curve, maturity)
    lower_rate = float(curve[lower_key])
    upper_rate = float(curve[upper_key])
    if lower == upper:
        return lower_rate
    weight = maturity - lower
    return lower_rate + (upper_rate - lower_rate) * weight


def fitted_zero_rate(curve: dict[str, float | str], maturity: float) -> float:
    beta0 = float(curve["BETA0"])
    beta1 = float(curve["BETA1"])
    beta2 = float(curve["BETA2"])
    beta3 = float(curve.get("BETA3", 0.0))
    tau1 = float(curve["TAU1"])
    tau2 = float(curve.get("TAU2", -999.99))

    x1 = maturity / tau1
    factor1 = (1.0 - math.exp(-x1)) / x1
    factor2 = factor1 - math.exp(-x1)
    value = beta0 + beta1 * factor1 + beta2 * factor2
    if tau2 > 0 and beta3 != 0:
        x2 = maturity / tau2
        factor3 = (1.0 - math.exp(-x2)) / x2 - math.exp(-x2)
        value += beta3 * factor3
    return value / 100.0


def price_coupon_bond_from_zero_curve(curve: dict[str, float | str], coupon_rate: float, maturity_years: float) -> float:
    coupon = coupon_rate / 2.0 * 100.0
    periods = max(1, int(math.ceil(maturity_years * 2)))
    price = 0.0
    for period in range(1, periods + 1):
        cashflow_time = min(period / 2.0, maturity_years)
        cashflow = coupon
        if period == periods:
            cashflow += 100.0
        zero_rate = interpolated_zero_rate(curve, cashflow_time)
        price += cashflow * math.exp(-zero_rate * cashflow_time)
    return price


def build_fed_synthetic_rows(fed_rows: list[dict[str, float | str]], stop_before: str) -> dict[str, dict[str, float | str]]:
    eligible = [row for row in fed_rows if str(row["Date"]) < stop_before]
    rows: dict[str, dict[str, float | str]] = {}
    previous_curve: dict[str, float | str] | None = None
    close_level = 100.0
    adjusted_level = 100.0
    for curve in eligible:
        day = str(curve["Date"])
        if previous_curve is None:
            rows[day] = {"Date": day, "Close": close_level, "Adj Close": adjusted_level}
        else:
            coupon_rate = interpolated_zero_rate(previous_curve, SYNTHETIC_MATURITY_YEARS)
            previous_price = price_coupon_bond_from_zero_curve(
                previous_curve, coupon_rate, SYNTHETIC_MATURITY_YEARS
            )
            current_maturity = SYNTHETIC_MATURITY_YEARS - 1.0 / 365.25
            current_price = price_coupon_bond_from_zero_curve(curve, coupon_rate, current_maturity)
            coupon_carry = coupon_rate * 100.0 / 365.25
            close_level *= current_price / previous_price
            adjusted_level *= (current_price + coupon_carry) / previous_price
            rows[day] = {
                "Date": day,
                "Close": close_level,
                "Adj Close": adjusted_level,
            }
        previous_curve = curve
    return rows


def build_normalized_rows(
    fed_rows: list[dict[str, float | str]],
    vfitx_rows: list[dict],
    ief_rows: list[dict],
) -> list[dict[str, str]]:
    by_source = {
        VFITX_SYMBOL: {row["Date"]: row for row in vfitx_rows},
        IEF_SYMBOL: {row["Date"]: row for row in ief_rows},
    }
    vfitx_dates = sorted(by_source[VFITX_SYMBOL])
    if len(vfitx_dates) < 2:
        raise RuntimeError("VFITX history is too short to splice")
    vfitx_return_start = vfitx_dates[1]
    by_source["FED8PT5Y"] = build_fed_synthetic_rows(fed_rows, vfitx_return_start)
    ief_dates = sorted(by_source[IEF_SYMBOL])
    if len(ief_dates) < 2:
        raise RuntimeError("IEF history is too short to splice")
    ief_return_start = ief_dates[1]

    dates = sorted(
        set(by_source["FED8PT5Y"])
        | {day for day in by_source[VFITX_SYMBOL] if vfitx_return_start <= day < ief_return_start}
        | {day for day in by_source[IEF_SYMBOL] if day >= ief_return_start}
    )
    rows: list[dict[str, str]] = []
    close_index = 100.0
    adjusted_index = 100.0
    previous_source_row: dict | None = None
    previous_source_symbol: str | None = None

    for day in dates:
        if day >= ief_return_start and day in by_source[IEF_SYMBOL]:
            source_symbol = IEF_SYMBOL
        elif day >= vfitx_return_start and day in by_source[VFITX_SYMBOL]:
            source_symbol = VFITX_SYMBOL
        else:
            source_symbol = "FED8PT5Y"
        current = by_source[source_symbol].get(day)
        if current is None:
            continue

        if previous_source_row is None:
            price_return = None
            total_return = None
        elif previous_source_symbol == source_symbol:
            price_return = float(current["Close"]) / float(previous_source_row["Close"]) - 1
            total_return = float(current["Adj Close"]) / float(previous_source_row["Adj Close"]) - 1
            close_index *= 1 + price_return
            adjusted_index *= 1 + total_return
        else:
            prior_in_new_source = by_source[source_symbol].get(previous_source_row["Date"])
            if prior_in_new_source is None:
                raise RuntimeError(f"No overlap row for source switch on {day}")
            price_return = float(current["Close"]) / float(prior_in_new_source["Close"]) - 1
            total_return = float(current["Adj Close"]) / float(prior_in_new_source["Adj Close"]) - 1
            close_index *= 1 + price_return
            adjusted_index *= 1 + total_return

        if source_symbol == IEF_SYMBOL:
            flag = IEF_FLAG
            notes = IEF_NOTES
            source_label = "Yahoo Finance chart API (IEF)"
        elif source_symbol == VFITX_SYMBOL:
            flag = VFITX_FLAG
            notes = VFITX_NOTES
            source_label = "Yahoo Finance chart API (VFITX)"
        else:
            flag = FED_SYNTHETIC_FLAG
            notes = FED_SYNTHETIC_NOTES
            source_label = "Federal Reserve nominal yield curve model"
        rows.append(
            {
                "Date": day,
                "Open": "",
                "High": "",
                "Low": "",
                "Close": round_float(close_index),
                "Adj Close": round_float(adjusted_index),
                "Volume": "",
                "Price Return": "" if price_return is None else round_float(price_return),
                "Total Return": "" if total_return is None else round_float(total_return),
                "Source": source_label,
                "Quality Flag": flag,
                "Source Notes": notes,
            }
        )
        previous_source_row = current
        previous_source_symbol = source_symbol

    return rows


def write_csv(path: Path, rows: list[dict[str, str]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=OUTPUT_COLUMNS)
        writer.writeheader()
        writer.writerows(rows)


def write_parquet_if_available(csv_path: Path, parquet_path: Path) -> bool:
    try:
        import pandas as pd
    except ImportError:
        return False
    try:
        frame = pd.read_csv(csv_path, parse_dates=["Date"])
        frame.to_parquet(parquet_path, index=False)
    except (ImportError, ModuleNotFoundError):
        return False
    return True


def checksum(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def write_build_metadata(path: Path, rows: list[dict[str, str]], csv_path: Path, parquet_written: bool) -> None:
    metadata = {
        "asset_id": ASSET_ID,
        "asset_name": ASSET_NAME,
        "source": SOURCE,
        "build_timestamp_utc": datetime.now(timezone.utc).isoformat(),
        "row_count": len(rows),
        "first_date": rows[0]["Date"] if rows else None,
        "last_date": rows[-1]["Date"] if rows else None,
        "csv_path": csv_path.relative_to(path.parent.parent.parent).as_posix(),
        "csv_sha256": checksum(csv_path),
        "parquet_written": parquet_written,
        "quality_flags": sorted({row["Quality Flag"] for row in rows}),
        "notes": (
            "IEF-like intermediate Treasury total-return proxy. Federal Reserve nominal yield curves are used for a "
            "synthetic 8.5-year par Treasury segment before VFITX; VFITX is used before IEF daily history is available."
        ),
    }
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(metadata, indent=2) + "\n", encoding="utf-8")


def main() -> None:
    args = parse_args()
    root = Path(args.root)
    end_date = date.fromisoformat(args.end_date)
    raw_dir = root / "sources" / "raw"
    raw_dir.mkdir(parents=True, exist_ok=True)

    fed_csv = fetch_fed_nominal_yield_curve()
    vfitx_payload = fetch_chart(VFITX_SYMBOL, end_date)
    ief_payload = fetch_chart(IEF_SYMBOL, end_date)
    (raw_dir / f"{ASSET_ID}_fed_nominal_yield_curve.csv").write_text(fed_csv, encoding="utf-8")
    (raw_dir / f"{ASSET_ID}_yahoo_vfitx_chart.json").write_text(json.dumps(vfitx_payload), encoding="utf-8")
    (raw_dir / f"{ASSET_ID}_yahoo_ief_chart.json").write_text(json.dumps(ief_payload), encoding="utf-8")

    rows = build_normalized_rows(
        parse_fed_yield_curve_csv(fed_csv, end_date),
        chart_rows(vfitx_payload),
        chart_rows(ief_payload),
    )
    if not rows:
        raise RuntimeError("No intermediate-term Treasury rows generated")

    interim_csv = root / "data" / "interim" / f"{ASSET_ID}.csv"
    processed_csv = root / "data" / "processed" / f"{ASSET_ID}.csv"
    processed_parquet = root / "data" / "processed" / f"{ASSET_ID}.parquet"

    write_csv(interim_csv, rows)
    write_csv(processed_csv, rows)
    parquet_written = write_parquet_if_available(processed_csv, processed_parquet)
    write_build_metadata(root / "sources" / "manifests" / f"{ASSET_ID}_build.json", rows, processed_csv, parquet_written)

    print(f"Wrote {len(rows)} rows to {processed_csv}")
    print(f"First date: {rows[0]['Date']}; last date: {rows[-1]['Date']}")
    if parquet_written:
        print(f"Wrote Parquet to {processed_parquet}")
    else:
        print("Parquet not written because pandas/pyarrow is unavailable")


if __name__ == "__main__":
    main()
