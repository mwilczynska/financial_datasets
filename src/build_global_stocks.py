"""Build a long-horizon global all-world stock total-return proxy dataset."""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import math
import zipfile
from datetime import date, datetime, time, timedelta, timezone
from decimal import Decimal, getcontext
from pathlib import Path
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

import requests

getcontext().prec = 40

ASSET_ID = "global_stocks"
ASSET_NAME = "Global All-World Stocks Total-Return Proxy"
ALIAS = "GLSTOCK"

START_DATE = date(1970, 1, 1)
KEN_FRENCH_DEVELOPED_DAILY_URL = (
    "https://mba.tuck.dartmouth.edu/pages/faculty/ken.french/ftp/Developed_3_Factors_Daily_CSV.zip"
)
KEN_FRENCH_ZIP_NAME = "Developed_3_Factors_Daily_CSV.zip"
KEN_FRENCH_CSV_NAME = "Developed_3_Factors_Daily.csv"
VT_SYMBOL = "VT"
VT_FETCH_START = date(2008, 1, 1)

YAHOO_COLUMNS = ["Date", "Open", "High", "Low", "Close", "Adj Close", "Volume"]
PROJECT_COLUMNS = ["Price Return", "Total Return", "Source", "Quality Flag", "Source Notes"]
OUTPUT_COLUMNS = YAHOO_COLUMNS + PROJECT_COLUMNS

MSCI_ANNUAL_SCALED_FLAG = "model_msci_world_annual_return_scaled_uslcap_daily_proxy"
USLCAP_GAP_FLAG = "model_uslcap_daily_proxy_gap_until_ff_developed_daily"
FF_DEVELOPED_FLAG = "observed_fama_french_developed_market_total_return"
VT_FLAG = "observed_vt_etf_adjusted_total_return"

MSCI_ANNUAL_SOURCE = "MSCI World gross annual total returns + USLCAP daily path proxy"
USLCAP_GAP_SOURCE = "USLCAP daily total-return proxy"
FF_DEVELOPED_SOURCE = "Kenneth French Data Library Developed 3 Factors Daily"
VT_SOURCE = "Yahoo Finance chart API (VT adjusted-close total return)"

MSCI_ANNUAL_NOTES = (
    "1970-1989 model segment. Uses USLCAP daily total-return path adjusted by a constant "
    "calendar-year log-return overlay so each year matches published MSCI World gross annual "
    "total return. Model-derived; not observed daily global index history."
)
USLCAP_GAP_NOTES = (
    "1990 pre-Fama/French gap fill. Uses USLCAP daily total returns until developed-market "
    "daily factors begin. Model-derived and U.S.-biased."
)
FF_DEVELOPED_NOTES = (
    "Daily developed-market total return from Fama/French Developed 3 Factors: Mkt-RF + RF. "
    "Developed markets only; excludes emerging markets and is not an investable ETF."
)
VT_NOTES = (
    "Observed Vanguard Total World Stock ETF adjusted-close total return via Yahoo. "
    "Includes developed and emerging markets, net of ETF expenses."
)

# Public annual MSCI World gross total returns used only to anchor the 1970-1989 model segment.
# Source notes are recorded in methodology/source files. Values are decimal returns.
MSCI_WORLD_GROSS_ANNUAL_RETURNS = {
    1970: Decimal("-0.0198"),
    1971: Decimal("0.1956"),
    1972: Decimal("0.2355"),
    1973: Decimal("-0.1451"),
    1974: Decimal("-0.2448"),
    1975: Decimal("0.3450"),
    1976: Decimal("0.1471"),
    1977: Decimal("0.0500"),
    1978: Decimal("0.1822"),
    1979: Decimal("0.1267"),
    1980: Decimal("0.2772"),
    1981: Decimal("-0.0330"),
    1982: Decimal("0.1127"),
    1983: Decimal("0.2328"),
    1984: Decimal("0.0577"),
    1985: Decimal("0.4177"),
    1986: Decimal("0.4280"),
    1987: Decimal("0.1676"),
    1988: Decimal("0.2395"),
    1989: Decimal("0.1719"),
}


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


def _exchange_tz(meta: dict):
    timezone_name = meta.get("exchangeTimezoneName", "America/New_York")
    try:
        return ZoneInfo(timezone_name)
    except ZoneInfoNotFoundError:
        return timezone(timedelta(seconds=int(meta.get("gmtoffset", 0))))


def close_series(payload: dict, field: str = "adjclose") -> dict[str, float]:
    result = payload["chart"]["result"][0]
    timestamps = result.get("timestamp") or []
    quote = result["indicators"]["quote"][0]
    adjclose = result.get("indicators", {}).get("adjclose", [{}])[0].get("adjclose", [])
    exchange_tz = _exchange_tz(result.get("meta", {}))

    values: dict[str, float] = {}
    for index, timestamp in enumerate(timestamps):
        if field == "adjclose":
            value = adjclose[index] if index < len(adjclose) else None
        else:
            value = quote.get(field, [None])[index]
        if value is None:
            continue
        day = datetime.fromtimestamp(timestamp, exchange_tz).date().isoformat()
        values[day] = float(value)
    return values


def fetch_ken_french_zip(raw_dir: Path) -> Path:
    raw_dir.mkdir(parents=True, exist_ok=True)
    path = raw_dir / KEN_FRENCH_ZIP_NAME
    response = requests.get(KEN_FRENCH_DEVELOPED_DAILY_URL, timeout=60, headers={"User-Agent": "Mozilla/5.0"})
    response.raise_for_status()
    path.write_bytes(response.content)
    return path


def load_ff_developed_returns(zip_path: Path) -> dict[str, Decimal]:
    with zipfile.ZipFile(zip_path) as archive:
        text = archive.read(KEN_FRENCH_CSV_NAME).decode("utf-8", errors="replace")

    returns: dict[str, Decimal] = {}
    reader = csv.reader(text.splitlines())
    header_seen = False
    for raw_row in reader:
        if not raw_row:
            continue
        first = raw_row[0].strip()
        if first == "":
            header_seen = True
            continue
        if not header_seen or not first.isdigit() or len(first) != 8:
            continue
        mkt_rf = Decimal(raw_row[1].strip())
        rf = Decimal(raw_row[4].strip())
        if mkt_rf == Decimal("-99.99") or rf == Decimal("-99.99"):
            continue
        parsed = date(int(first[:4]), int(first[4:6]), int(first[6:8])).isoformat()
        returns[parsed] = (mkt_rf + rf) / Decimal("100")
    if not returns:
        raise RuntimeError("No Fama/French developed-market daily returns parsed")
    return returns


def load_uslcap_returns(path: Path) -> list[tuple[str, Decimal | None]]:
    if not path.exists():
        raise RuntimeError(f"USLCAP base dataset not found: {path}")
    rows: list[tuple[str, Decimal | None]] = []
    with path.open(newline="", encoding="utf-8") as handle:
        for row in csv.DictReader(handle):
            tr = row["Total Return"].strip()
            rows.append((row["Date"], Decimal(tr) if tr else None))
    rows.sort(key=lambda item: item[0])
    return rows


def annual_scaled_uslcap_returns(uslcap: list[tuple[str, Decimal | None]], end_before: str) -> dict[str, Decimal]:
    by_year: dict[int, list[tuple[str, Decimal]]] = {}
    for day, ret in uslcap:
        parsed = date.fromisoformat(day)
        if parsed.year not in MSCI_WORLD_GROSS_ANNUAL_RETURNS or day >= end_before or ret is None:
            continue
        by_year.setdefault(parsed.year, []).append((day, ret))

    scaled: dict[str, Decimal] = {}
    for year, items in by_year.items():
        us_growth = Decimal("1")
        for _, ret in items:
            us_growth *= Decimal("1") + ret
        target_growth = Decimal("1") + MSCI_WORLD_GROSS_ANNUAL_RETURNS[year]
        daily_log_overlay = (target_growth.ln() - us_growth.ln()) / Decimal(len(items))
        daily_multiplier = Decimal(str(math.exp(float(daily_log_overlay))))
        for day, ret in items:
            scaled[day] = (Decimal("1") + ret) * daily_multiplier - Decimal("1")
    return scaled


def round_decimal(value: Decimal) -> str:
    return f"{value:.10f}".rstrip("0").rstrip(".")


def build_rows(
    uslcap_returns: list[tuple[str, Decimal | None]],
    ff_returns: dict[str, Decimal],
    vt_adj: dict[str, float],
    end_date: date,
) -> tuple[list[dict[str, str]], dict]:
    ff_start = min(ff_returns)
    vt_dates = sorted(vt_adj)
    if not vt_dates:
        raise RuntimeError("No VT adjusted-close data fetched")
    vt_inception = vt_dates[0]
    annual_scaled = annual_scaled_uslcap_returns(uslcap_returns, ff_start)

    all_dates = sorted({
        day for day, _ in uslcap_returns if START_DATE.isoformat() <= day <= end_date.isoformat()
    } | {day for day in ff_returns if day <= end_date.isoformat()} | {day for day in vt_adj if day <= end_date.isoformat()})

    uslcap = dict(uslcap_returns)
    rows: list[dict[str, str]] = []
    level = Decimal("100")
    previous_vt_adj: float | None = None
    segment_counts: dict[str, int] = {}

    for current in all_dates:
        if current < START_DATE.isoformat() or current > end_date.isoformat():
            continue

        if not rows:
            rows.append(_row(current, level, "", MSCI_ANNUAL_SCALED_FLAG, MSCI_ANNUAL_SOURCE, MSCI_ANNUAL_NOTES))
            if current in vt_adj:
                previous_vt_adj = vt_adj[current]
            segment_counts[MSCI_ANNUAL_SCALED_FLAG] = segment_counts.get(MSCI_ANNUAL_SCALED_FLAG, 0) + 1
            continue

        if current > vt_inception and current in vt_adj and previous_vt_adj is not None:
            daily_return = Decimal(str(vt_adj[current])) / Decimal(str(previous_vt_adj)) - Decimal("1")
            flag, source, notes = VT_FLAG, VT_SOURCE, VT_NOTES
        elif current in ff_returns and current <= vt_inception:
            daily_return = ff_returns[current]
            flag, source, notes = FF_DEVELOPED_FLAG, FF_DEVELOPED_SOURCE, FF_DEVELOPED_NOTES
        elif current in annual_scaled:
            daily_return = annual_scaled[current]
            flag, source, notes = MSCI_ANNUAL_SCALED_FLAG, MSCI_ANNUAL_SOURCE, MSCI_ANNUAL_NOTES
        elif current < ff_start and uslcap.get(current) is not None:
            daily_return = uslcap[current] or Decimal("0")
            flag, source, notes = USLCAP_GAP_FLAG, USLCAP_GAP_SOURCE, USLCAP_GAP_NOTES
        else:
            continue

        level *= Decimal("1") + daily_return
        rows.append(_row(current, level, daily_return, flag, source, notes))
        segment_counts[flag] = segment_counts.get(flag, 0) + 1
        if current in vt_adj:
            previous_vt_adj = vt_adj[current]

    metadata = {
        "ff_developed_start": ff_start,
        "vt_inception": vt_inception,
        "segment_counts": segment_counts,
    }
    return rows, metadata


def _row(day: str, level: Decimal, daily_return: Decimal | str, flag: str, source: str, notes: str) -> dict[str, str]:
    ret = "" if daily_return == "" else round_decimal(daily_return)  # type: ignore[arg-type]
    return {
        "Date": day,
        "Open": "",
        "High": "",
        "Low": "",
        "Close": round_decimal(level),
        "Adj Close": round_decimal(level),
        "Volume": "",
        "Price Return": ret,
        "Total Return": ret,
        "Source": source,
        "Quality Flag": flag,
        "Source Notes": notes,
    }


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


def write_build_metadata(
    path: Path,
    rows: list[dict[str, str]],
    csv_path: Path,
    parquet_written: bool,
    extra: dict,
) -> None:
    metadata = {
        "asset_id": ASSET_ID,
        "asset_name": ASSET_NAME,
        "alias": ALIAS,
        "build_timestamp_utc": datetime.now(timezone.utc).isoformat(),
        "row_count": len(rows),
        "first_date": rows[0]["Date"] if rows else None,
        "last_date": rows[-1]["Date"] if rows else None,
        "csv_path": csv_path.relative_to(path.parent.parent.parent).as_posix(),
        "csv_sha256": checksum(csv_path),
        "parquet_written": parquet_written,
        "quality_flags": sorted({row["Quality Flag"] for row in rows}),
        **extra,
    }
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(metadata, indent=2) + "\n", encoding="utf-8")


def main() -> None:
    args = parse_args()
    root = Path(args.root)
    end_date = date.fromisoformat(args.end_date)

    raw_dir = root / "sources" / "raw"
    ff_zip = fetch_ken_french_zip(raw_dir)
    vt_payload = fetch_chart(VT_SYMBOL, end_date, VT_FETCH_START)
    vt_raw = raw_dir / f"{ASSET_ID}_yahoo_vt_chart.json"
    vt_raw.write_text(json.dumps(vt_payload), encoding="utf-8")

    uslcap_returns = load_uslcap_returns(root / "data" / "processed" / "us_large_cap_sp500.csv")
    ff_returns = load_ff_developed_returns(ff_zip)
    vt_adj = close_series(vt_payload, "adjclose")
    rows, extra = build_rows(uslcap_returns, ff_returns, vt_adj, end_date)
    if not rows:
        raise RuntimeError("No global stock rows were built")

    interim_csv = root / "data" / "interim" / f"{ASSET_ID}.csv"
    processed_csv = root / "data" / "processed" / f"{ASSET_ID}.csv"
    processed_parquet = root / "data" / "processed" / f"{ASSET_ID}.parquet"
    write_csv(interim_csv, rows)
    write_csv(processed_csv, rows)
    parquet_written = write_parquet_if_available(processed_csv, processed_parquet)
    write_build_metadata(root / "sources" / "manifests" / f"{ASSET_ID}_build.json", rows, processed_csv, parquet_written, extra)

    print(f"Wrote {len(rows)} rows to {processed_csv}")
    print(f"Date range: {rows[0]['Date']} to {rows[-1]['Date']}")
    print(f"Segments: {extra['segment_counts']}")
    if parquet_written:
        print(f"Wrote Parquet to {processed_parquet}")
    else:
        print("Parquet not written because pandas/pyarrow is unavailable")


if __name__ == "__main__":
    main()
