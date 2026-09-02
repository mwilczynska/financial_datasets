"""Build a daily CPI inflation index from monthly BLS CPI-U observations."""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import math
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

import requests


ASSET_ID = "cpi_inflation"
ASSET_NAME = "U.S. CPI-U Inflation Index"
ALIAS = "CPI"
BLS_SERIES = "CUSR0000SA0"
BLS_API_URL = "https://api.bls.gov/publicAPI/v2/timeseries/data/"
START_DATE = date(1970, 1, 1)
YAHOO_COLUMNS = ["Date", "Open", "High", "Low", "Close", "Adj Close", "Volume"]
PROJECT_COLUMNS = ["Price Return", "Total Return", "Source", "Quality Flag", "Source Notes"]
OUTPUT_COLUMNS = YAHOO_COLUMNS + PROJECT_COLUMNS

SOURCE = "BLS CUSR0000SA0 (monthly CPI-U, seasonally adjusted)"
MONTHLY_FLAG = "observed_bls_monthly_cpi_u_level"
INTERPOLATED_FLAG = "model_daily_log_interpolated_monthly_cpi_u"
CARRY_FLAG = "carried_forward_latest_monthly_cpi_u_level"
MONTHLY_NOTES = "Exact monthly BLS CUSR0000SA0 observation date. CPI-U seasonally adjusted index, 1982-84=100."
INTERPOLATED_NOTES = (
    "Daily CPI level derived from adjacent monthly BLS CUSR0000SA0 observations using constant log "
    "daily interpolation. This is not an observed daily inflation print."
)
CARRY_NOTES = (
    "Latest available monthly BLS CUSR0000SA0 level carried forward after the most recent BLS "
    "observation. Revise by rerunning the build after BLS publishes the next month."
)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--end-date", default=date.today().isoformat(), help="Inclusive end date, YYYY-MM-DD.")
    parser.add_argument("--root", default=".", help="Project root.")
    return parser.parse_args()


def fetch_bls_chunk(start_year: int, end_year: int) -> dict:
    payload = {"seriesid": [BLS_SERIES], "startyear": str(start_year), "endyear": str(end_year)}
    response = requests.post(BLS_API_URL, json=payload, timeout=60, headers={"User-Agent": "Mozilla/5.0"})
    response.raise_for_status()
    body = response.json()
    if body.get("status") != "REQUEST_SUCCEEDED":
        raise RuntimeError(f"BLS API request failed for {start_year}-{end_year}: {body}")
    return body


def fetch_bls_payload(end_date: date) -> list[dict]:
    payloads: list[dict] = []
    start_year = START_DATE.year
    while start_year <= end_date.year:
        end_year = min(start_year + 9, end_date.year)
        payloads.append(fetch_bls_chunk(start_year, end_year))
        start_year = end_year + 1
    return payloads


def parse_bls_monthly(payloads: list[dict]) -> list[tuple[date, float]]:
    values: dict[date, float] = {}
    for payload in payloads:
        series_list = payload.get("Results", {}).get("series", [])
        if not series_list:
            continue
        for row in series_list[0].get("data", []):
            period = row.get("period", "")
            if not period.startswith("M"):
                continue
            month = int(period[1:])
            if not 1 <= month <= 12:
                continue
            raw_value = str(row.get("value", "")).strip()
            if not raw_value or raw_value == "-":
                continue
            obs_date = date(int(row["year"]), month, 1)
            if obs_date >= START_DATE:
                values[obs_date] = float(raw_value)
    rows = sorted(values.items(), key=lambda item: item[0])
    if not rows:
        raise RuntimeError("No usable BLS CPI observations parsed")
    return rows


def round_float(value: float | None) -> str:
    if value is None:
        return ""
    return f"{float(value):.10f}".rstrip("0").rstrip(".")


def daily_cpi_level(day: date, monthly: list[tuple[date, float]]) -> tuple[float, str, str]:
    for index, (obs_day, obs_value) in enumerate(monthly):
        if day == obs_day:
            return obs_value, MONTHLY_FLAG, MONTHLY_NOTES
        if index + 1 >= len(monthly):
            continue
        next_day, next_value = monthly[index + 1]
        if obs_day < day < next_day:
            span = (next_day - obs_day).days
            offset = (day - obs_day).days
            level = math.exp(math.log(next_value / obs_value) * offset / span) * obs_value
            return level, INTERPOLATED_FLAG, INTERPOLATED_NOTES

    last_day, last_value = monthly[-1]
    if day > last_day:
        return last_value, CARRY_FLAG, CARRY_NOTES

    raise RuntimeError(f"No CPI observation bracket found for {day.isoformat()}")


def build_rows(monthly: list[tuple[date, float]], end_date: date) -> list[dict[str, str]]:
    rows: list[dict[str, str]] = []
    previous_level: float | None = None
    current = START_DATE
    while current <= end_date:
        level, flag, notes = daily_cpi_level(current, monthly)
        daily_return = "" if previous_level is None else round_float(level / previous_level - 1)
        previous_level = level
        rows.append(
            {
                "Date": current.isoformat(),
                "Open": "",
                "High": "",
                "Low": "",
                "Close": round_float(level),
                "Adj Close": round_float(level),
                "Volume": "",
                "Price Return": daily_return,
                "Total Return": daily_return,
                "Source": SOURCE,
                "Quality Flag": flag,
                "Source Notes": notes,
            }
        )
        current += timedelta(days=1)
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


def write_build_metadata(
    path: Path,
    rows: list[dict[str, str]],
    monthly: list[tuple[date, float]],
    csv_path: Path,
    parquet_written: bool,
) -> None:
    metadata = {
        "asset_id": ASSET_ID,
        "asset_name": ASSET_NAME,
        "alias": ALIAS,
        "source": SOURCE,
        "source_url": BLS_API_URL,
        "source_series": BLS_SERIES,
        "build_timestamp_utc": datetime.now(timezone.utc).isoformat(),
        "row_count": len(rows),
        "first_date": rows[0]["Date"] if rows else None,
        "last_date": rows[-1]["Date"] if rows else None,
        "latest_monthly_observation": monthly[-1][0].isoformat(),
        "csv_path": csv_path.relative_to(path.parent.parent.parent).as_posix(),
        "csv_sha256": checksum(csv_path),
        "parquet_written": parquet_written,
        "quality_flags": sorted({row["Quality Flag"] for row in rows}),
        "notes": "Calendar-daily CPI deflator derived from monthly BLS CUSR0000SA0 observations.",
    }
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(metadata, indent=2) + "\n", encoding="utf-8")


def main() -> None:
    args = parse_args()
    root = Path(args.root)
    end_date = date.fromisoformat(args.end_date)
    if end_date < START_DATE:
        raise RuntimeError(f"End date {end_date.isoformat()} is before {START_DATE.isoformat()}")

    raw_payload = fetch_bls_payload(end_date)
    raw_path = root / "sources" / "raw" / f"{ASSET_ID}_bls_{BLS_SERIES}.json"
    raw_path.parent.mkdir(parents=True, exist_ok=True)
    raw_path.write_text(json.dumps(raw_payload, indent=2), encoding="utf-8")

    monthly = parse_bls_monthly(raw_payload)
    rows = build_rows(monthly, end_date)

    interim_csv = root / "data" / "interim" / f"{ASSET_ID}.csv"
    processed_csv = root / "data" / "processed" / f"{ASSET_ID}.csv"
    processed_parquet = root / "data" / "processed" / f"{ASSET_ID}.parquet"

    write_csv(interim_csv, rows)
    write_csv(processed_csv, rows)
    parquet_written = write_parquet_if_available(processed_csv, processed_parquet)
    write_build_metadata(
        root / "sources" / "manifests" / f"{ASSET_ID}_build.json",
        rows,
        monthly,
        processed_csv,
        parquet_written,
    )

    print(f"Wrote {len(rows)} rows to {processed_csv}")
    print(f"Date range: {rows[0]['Date']} to {rows[-1]['Date']}")
    print(f"Latest monthly CPI observation: {monthly[-1][0].isoformat()}")
    if parquet_written:
        print(f"Wrote Parquet to {processed_parquet}")
    else:
        print("Parquet not written because pandas/pyarrow is unavailable")


if __name__ == "__main__":
    main()
