"""Build the initial Yahoo-compatible U.S. large-cap equity dataset."""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import zipfile
from datetime import date, datetime, time, timedelta, timezone
from decimal import Decimal
from pathlib import Path
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

import requests


ASSET_ID = "us_large_cap_sp500"
SYMBOL = "^GSPC"
TOTAL_RETURN_SYMBOL = "^SP500TR"
YAHOO_PRICE_SYMBOL = "%5EGSPC"
YAHOO_TOTAL_RETURN_SYMBOL = "%5ESP500TR"
KEN_FRENCH_SIZE_PORTFOLIOS_URL = (
    "https://mba.tuck.dartmouth.edu/pages/faculty/ken.french/ftp/Portfolios_Formed_on_ME_daily_CSV.zip"
)
KEN_FRENCH_ZIP_NAME = "Portfolios_Formed_on_ME_daily_CSV.zip"
KEN_FRENCH_CSV_NAME = "Portfolios_Formed_on_ME_daily.csv"
KEN_FRENCH_TOTAL_RETURN_COLUMN = "Hi 30"
START_DATE = date(1970, 1, 1)
MAX_START_LAG_DAYS = 7
YAHOO_COLUMNS = ["Date", "Open", "High", "Low", "Close", "Adj Close", "Volume"]
PROJECT_COLUMNS = ["Price Return", "Total Return", "Source", "Quality Flag", "Source Notes"]
OUTPUT_COLUMNS = YAHOO_COLUMNS + PROJECT_COLUMNS
SOURCE = "Yahoo Finance chart API (^GSPC price; ^SP500TR total return)"
TOTAL_RETURN_FRENCH_FLAG = "observed_price_index_crsp_large_cap_total_return"
TOTAL_RETURN_SP500TR_FLAG = "observed_price_index_sp500_total_return"
TOTAL_RETURN_FRENCH_NOTES = "Close is ^GSPC price index; Adj Close compounds Kenneth French/CRSP Hi 30 daily total returns."
TOTAL_RETURN_SP500TR_NOTES = "Close is ^GSPC price index; Adj Close compounds ^SP500TR daily total-return index returns."


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
        raise RuntimeError(f"Yahoo chart error: {error}")
    return payload


def fetch_ken_french_zip(raw_dir: Path) -> Path:
    raw_dir.mkdir(parents=True, exist_ok=True)
    path = raw_dir / KEN_FRENCH_ZIP_NAME
    if path.exists():
        return path

    response = requests.get(KEN_FRENCH_SIZE_PORTFOLIOS_URL, timeout=60, headers={"User-Agent": "Mozilla/5.0"})
    response.raise_for_status()
    path.write_bytes(response.content)
    return path


def round_float(value: float | None) -> str:
    if value is None:
        return ""
    return f"{float(value):.10f}".rstrip("0").rstrip(".")


def round_decimal(value: Decimal) -> str:
    return f"{value:.10f}".rstrip("0").rstrip(".")


def chart_rows(payload: dict) -> list[dict[str, str]]:
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

    rows: list[dict[str, str]] = []
    previous_close: float | None = None
    for index, timestamp in enumerate(timestamps):
        close = quote.get("close", [None])[index]
        if close is None:
            continue

        day = datetime.fromtimestamp(timestamp, exchange_tz).date().isoformat()
        price_return = "" if previous_close is None else round_float(float(close) / previous_close - 1)
        previous_close = float(close)

        rows.append(
            {
                "Date": day,
                "Open": round_float(quote.get("open", [None])[index]),
                "High": round_float(quote.get("high", [None])[index]),
                "Low": round_float(quote.get("low", [None])[index]),
                "Close": round_float(close),
                "Adj Close": "",
                "Volume": "" if quote.get("volume", [None])[index] is None else str(quote["volume"][index]),
                "Price Return": price_return,
                "Total Return": "",
                "Source": SOURCE,
                "Quality Flag": "",
                "Source Notes": "",
            }
        )
    return rows


def close_by_date(payload: dict) -> dict[str, float]:
    result = payload["chart"]["result"][0]
    timestamps = result.get("timestamp") or []
    quote = result["indicators"]["quote"][0]
    meta = result.get("meta", {})
    timezone_name = meta.get("exchangeTimezoneName", "America/New_York")
    try:
        exchange_tz = ZoneInfo(timezone_name)
    except ZoneInfoNotFoundError:
        exchange_tz = timezone(timedelta(seconds=int(meta.get("gmtoffset", 0))))

    values: dict[str, float] = {}
    for index, timestamp in enumerate(timestamps):
        close = quote.get("close", [None])[index]
        if close is None:
            continue
        day = datetime.fromtimestamp(timestamp, exchange_tz).date().isoformat()
        values[day] = float(close)
    return values


def load_ken_french_hi30_returns(zip_path: Path) -> dict[str, Decimal]:
    with zipfile.ZipFile(zip_path) as archive:
        text = archive.read(KEN_FRENCH_CSV_NAME).decode("utf-8", errors="replace")

    lines = text.splitlines()
    header_index = next(
        index for index, line in enumerate(lines) if "Average Value Weighted Returns -- Daily" in line
    ) + 1
    header = [column.strip() for column in lines[header_index].split(",")]
    hi30_index = header.index(KEN_FRENCH_TOTAL_RETURN_COLUMN)

    returns: dict[str, Decimal] = {}
    for line in lines[header_index + 1 :]:
        if not line.strip():
            break
        parts = [part.strip() for part in line.split(",")]
        raw_date = parts[0]
        if not raw_date.isdigit() or len(raw_date) != 8:
            break
        raw_return = Decimal(parts[hi30_index])
        if raw_return in {Decimal("-99.99"), Decimal("-999")}:
            continue
        parsed_date = date(int(raw_date[:4]), int(raw_date[4:6]), int(raw_date[6:8])).isoformat()
        returns[parsed_date] = raw_return / Decimal("100")
    return returns


def add_total_return_adjustment(
    rows: list[dict[str, str]],
    french_returns: dict[str, Decimal],
    sp500tr_values: dict[str, float],
) -> list[dict[str, str]]:
    adjusted: Decimal | None = None
    previous_sp500tr: Decimal | None = None

    for row in rows:
        row_date = row["Date"]
        sp500tr = Decimal(str(sp500tr_values[row_date])) if row_date in sp500tr_values else None

        if adjusted is None:
            adjusted = Decimal(row["Close"])
            row["Adj Close"] = round_decimal(adjusted)
            row["Total Return"] = ""
            row["Quality Flag"] = TOTAL_RETURN_FRENCH_FLAG
            row["Source Notes"] = TOTAL_RETURN_FRENCH_NOTES
            previous_sp500tr = sp500tr
            continue

        if sp500tr is not None and previous_sp500tr is not None:
            total_return = sp500tr / previous_sp500tr - Decimal("1")
            row["Quality Flag"] = TOTAL_RETURN_SP500TR_FLAG
            row["Source Notes"] = TOTAL_RETURN_SP500TR_NOTES
        else:
            total_return = french_returns.get(row_date)
            if total_return is None:
                raise RuntimeError(f"Missing daily total-return source for {row_date}")
            row["Quality Flag"] = TOTAL_RETURN_FRENCH_FLAG
            row["Source Notes"] = TOTAL_RETURN_FRENCH_NOTES

        adjusted *= Decimal("1") + total_return
        row["Adj Close"] = round_decimal(adjusted)
        row["Total Return"] = round_decimal(total_return)
        previous_sp500tr = sp500tr
    return rows


def write_csv(path: Path, rows: list[dict[str, str]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=OUTPUT_COLUMNS)
        writer.writeheader()
        writer.writerows(rows)


def recompute_price_returns(rows: list[dict[str, str]]) -> list[dict[str, str]]:
    previous_close: float | None = None
    for row in rows:
        close = float(row["Close"])
        row["Price Return"] = "" if previous_close is None else round_float(close / previous_close - 1)
        previous_close = close
    return rows


def recompute_returns(rows: list[dict[str, str]]) -> list[dict[str, str]]:
    previous_close: float | None = None
    previous_adjusted: float | None = None
    for row in rows:
        close = float(row["Close"])
        row["Price Return"] = "" if previous_close is None else round_float(close / previous_close - 1)
        previous_close = close

        adjusted = float(row["Adj Close"])
        row["Total Return"] = "" if previous_adjusted is None else round_float(adjusted / previous_adjusted - 1)
        previous_adjusted = adjusted
    return rows


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
        "symbol": SYMBOL,
        "total_return_symbol": TOTAL_RETURN_SYMBOL,
        "source": SOURCE,
        "build_timestamp_utc": datetime.now(timezone.utc).isoformat(),
        "row_count": len(rows),
        "first_date": rows[0]["Date"] if rows else None,
        "last_date": rows[-1]["Date"] if rows else None,
        "csv_path": csv_path.relative_to(path.parent.parent.parent).as_posix(),
        "csv_sha256": checksum(csv_path),
        "parquet_written": parquet_written,
        "first_adjusted_date": next((row["Date"] for row in rows if row["Adj Close"]), None),
        "quality_flags": sorted({row["Quality Flag"] for row in rows}),
        "notes": "Close is ^GSPC price index; Adj Close compounds daily total returns from Kenneth French/CRSP Hi 30 before ^SP500TR can supply daily returns, then ^SP500TR thereafter.",
    }
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(metadata, indent=2) + "\n", encoding="utf-8")


def main() -> None:
    args = parse_args()
    root = Path(args.root)
    end_date = date.fromisoformat(args.end_date)
    raw_dir = root / "sources" / "raw"

    price_payload = fetch_chart(YAHOO_PRICE_SYMBOL, end_date)
    total_return_payload = fetch_chart(YAHOO_TOTAL_RETURN_SYMBOL, end_date)
    ken_french_zip = fetch_ken_french_zip(raw_dir)
    raw_path = raw_dir / f"{ASSET_ID}_yahoo_chart.json"
    raw_path.parent.mkdir(parents=True, exist_ok=True)
    raw_path.write_text(json.dumps(price_payload), encoding="utf-8")
    total_return_raw_path = raw_dir / f"{ASSET_ID}_yahoo_sp500tr_chart.json"
    total_return_raw_path.write_text(json.dumps(total_return_payload), encoding="utf-8")

    rows = chart_rows(price_payload)
    rows = add_total_return_adjustment(
        rows,
        load_ken_french_hi30_returns(ken_french_zip),
        close_by_date(total_return_payload),
    )
    if not rows:
        raise RuntimeError("No rows returned from Yahoo chart payload")
    first_date = date.fromisoformat(rows[0]["Date"])
    if first_date < START_DATE or first_date > START_DATE + timedelta(days=MAX_START_LAG_DAYS):
        raise RuntimeError(
            f"Dataset starts at {rows[0]['Date']}; expected first trading observation near {START_DATE.isoformat()}"
        )

    interim_csv = root / "data" / "interim" / f"{ASSET_ID}.csv"
    processed_csv = root / "data" / "processed" / f"{ASSET_ID}.csv"
    processed_parquet = root / "data" / "processed" / f"{ASSET_ID}.parquet"

    write_csv(interim_csv, rows)
    write_csv(processed_csv, rows)
    parquet_written = write_parquet_if_available(processed_csv, processed_parquet)
    write_build_metadata(root / "sources" / "manifests" / f"{ASSET_ID}_build.json", rows, processed_csv, parquet_written)

    print(f"Wrote {len(rows)} rows to {processed_csv}")
    if parquet_written:
        print(f"Wrote Parquet to {processed_parquet}")
    else:
        print("Parquet not written because pandas/pyarrow is unavailable")


if __name__ == "__main__":
    main()
