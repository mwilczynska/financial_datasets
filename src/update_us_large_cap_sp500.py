"""Incrementally update the U.S. large-cap equity dataset from Yahoo chart data."""

from __future__ import annotations

import argparse
import csv
from datetime import date, timedelta
from pathlib import Path

from build_us_large_cap_sp500 import (
    ASSET_ID,
    OUTPUT_COLUMNS,
    YAHOO_PRICE_SYMBOL,
    YAHOO_TOTAL_RETURN_SYMBOL,
    add_total_return_adjustment,
    chart_rows,
    close_by_date,
    fetch_chart,
    fetch_ken_french_zip,
    load_ken_french_hi30_returns,
    recompute_price_returns,
    write_build_metadata,
    write_csv,
    write_parquet_if_available,
)


OVERLAP_DAYS = 10


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--end-date", default=date.today().isoformat(), help="Inclusive end date, YYYY-MM-DD.")
    parser.add_argument("--root", default=".", help="Project root.")
    parser.add_argument("--overlap-days", type=int, default=OVERLAP_DAYS, help="Calendar-day overlap to refetch.")
    return parser.parse_args()


def read_existing(path: Path) -> list[dict[str, str]]:
    if not path.exists():
        return []
    with path.open(newline="", encoding="utf-8") as handle:
        reader = csv.DictReader(handle)
        rows = list(reader)
    missing = [column for column in OUTPUT_COLUMNS if column not in reader.fieldnames]
    if missing:
        raise RuntimeError(f"Existing dataset is missing columns: {missing}")
    return rows


def merge_rows(existing: list[dict[str, str]], new_rows: list[dict[str, str]]) -> list[dict[str, str]]:
    by_date = {row["Date"]: row for row in existing}
    by_date.update({row["Date"]: row for row in new_rows})
    merged = [by_date[key] for key in sorted(by_date)]
    for row in merged:
        row["Adj Close"] = ""
        row["Total Return"] = ""
        row["Quality Flag"] = ""
        row["Source Notes"] = ""
    return recompute_price_returns(merged)


def main() -> None:
    args = parse_args()
    root = Path(args.root)
    end_date = date.fromisoformat(args.end_date)
    processed_csv = root / "data" / "processed" / f"{ASSET_ID}.csv"
    interim_csv = root / "data" / "interim" / f"{ASSET_ID}.csv"
    processed_parquet = root / "data" / "processed" / f"{ASSET_ID}.parquet"
    raw_dir = root / "sources" / "raw"

    existing = read_existing(processed_csv)
    if existing:
        last_date = date.fromisoformat(existing[-1]["Date"])
        start_date = max(date(1970, 1, 1), last_date - timedelta(days=args.overlap_days))
    else:
        start_date = date(1970, 1, 1)

    price_payload = fetch_chart(YAHOO_PRICE_SYMBOL, end_date=end_date, start_date=start_date)
    total_return_payload = fetch_chart(YAHOO_TOTAL_RETURN_SYMBOL, end_date=end_date, start_date=start_date)
    new_rows = chart_rows(price_payload)
    merged = merge_rows(existing, new_rows)
    full_total_return_payload = fetch_chart(YAHOO_TOTAL_RETURN_SYMBOL, end_date=end_date)
    merged = add_total_return_adjustment(
        merged,
        load_ken_french_hi30_returns(fetch_ken_french_zip(raw_dir)),
        close_by_date(full_total_return_payload),
    )

    if not merged:
        raise RuntimeError("No rows available after update")

    write_csv(interim_csv, merged)
    write_csv(processed_csv, merged)
    parquet_written = write_parquet_if_available(processed_csv, processed_parquet)
    write_build_metadata(root / "sources" / "manifests" / f"{ASSET_ID}_build.json", merged, processed_csv, parquet_written)

    print(f"Existing rows: {len(existing)}")
    print(f"Fetched rows: {len(new_rows)} from {start_date.isoformat()} through {end_date.isoformat()}")
    print(f"Final rows: {len(merged)}")
    print(f"Wrote CSV to {processed_csv}")
    if parquet_written:
        print(f"Wrote Parquet to {processed_parquet}")
    else:
        print("Parquet not written because pandas/pyarrow is unavailable")


if __name__ == "__main__":
    main()
