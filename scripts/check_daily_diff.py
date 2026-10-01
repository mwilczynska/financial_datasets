"""Fail closed before publishing an unattended dataset refresh.

The baseline is a Git tree, never the local raw cache. Every processed dataset
is checked, including unchanged files. This gate replaces raw-history tests that
cannot run on an ephemeral hosted runner: history must remain unchanged, while
current observations must have matching, recent source responses.
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import io
import json
import math
import os
import subprocess
import sys
from datetime import date
from decimal import Decimal
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
from incremental_update import ASSETS, OUTPUT_COLUMNS, chart_rows  # noqa: E402

NUMERIC = ("Open", "High", "Low", "Close", "Adj Close", "Volume", "Price Return", "Total Return")
TEXT = ("Source", "Quality Flag", "Source Notes")


def fail(stem: str, message: str) -> None:
    raise RuntimeError(f"{stem}: {message}")


def read_csv(content: str, stem: str) -> list[dict[str, str]]:
    reader = csv.DictReader(io.StringIO(content))
    if reader.fieldnames != OUTPUT_COLUMNS:
        fail(stem, f"unexpected CSV columns {reader.fieldnames}")
    rows = list(reader)
    dates = [row["Date"] for row in rows]
    if not dates or dates != sorted(set(dates)):
        fail(stem, "empty, unsorted, or duplicate dates")
    for day in dates:
        date.fromisoformat(day)
    return rows


def source_record(root: Path, stem: str, symbol: str, end: date) -> dict[str, dict[str, float]]:
    path = root / "sources" / "raw" / "incremental" / f"{stem}_{symbol.lstrip('^').lower()}.json"
    if not path.is_file():
        fail(stem, f"missing current source response for {symbol}")
    payload = json.loads(path.read_text(encoding="utf-8"))
    result = (payload.get("chart", {}).get("result") or [None])[0]
    if not result or result.get("meta", {}).get("symbol") != symbol:
        fail(stem, f"source response has wrong symbol for {symbol}")
    rows = chart_rows(payload, require_adjusted=symbol not in ("^GSPC", "^SP500TR"))
    if not rows:
        fail(stem, f"empty current source response for {symbol}")
    latest = max(rows)
    if latest > end.isoformat() or (end - date.fromisoformat(latest)).days > 5:
        fail(stem, f"{symbol} source is stale or beyond target: {latest}")
    return rows


def quote_return(series: dict[str, dict[str, float]], day: str, field: str) -> float:
    previous = [key for key in series if key < day and field in series[key]]
    if not previous or day not in series:
        raise RuntimeError(f"Current source has no {field} comparison for {day}")
    return series[day][field] / series[max(previous)][field] - 1


def check_source_tail(stem: str, rows: list[dict[str, str]], windows: dict, root: Path,
                      metadata: dict, examined_days: set[str], monthly: list | None = None) -> None:
    asset = ASSETS[stem]
    examined_days.update(row["Date"] for row in rows[-10:])
    tail = [row for row in rows if row["Date"] in examined_days]
    for row in tail:
        day = row["Date"]
        kind = asset.kind
        price = total = None
        if kind == "cpi":
            from build_cpi_inflation import daily_cpi_level
            level, flag, _ = daily_cpi_level(date.fromisoformat(day), monthly)
            if abs(float(row["Close"]) - level) > 1e-8 or row["Quality Flag"] != flag:
                fail(stem, f"CPI level or flag disagrees with BLS on {day}")
            continue
        if kind == "uslcap":
            if day not in windows["^GSPC"] or day not in windows["^SP500TR"]:
                fail(stem, f"missing recent index observation on {day}")
            price = quote_return(windows["^GSPC"], day, "close")
            total = quote_return(windows["^SP500TR"], day, "close")
            if abs(float(row["Close"]) - windows["^GSPC"][day]["close"]) > 1e-5:
                fail(stem, f"S&P 500 level disagrees with source on {day}")
        elif kind in ("price_adj", "adj_only"):
            series = windows[asset.symbols[0]]
            if day not in series:
                fail(stem, f"missing recent ETF observation on {day}")
            total = quote_return(series, day, "adj")
            price = quote_return(series, day, "close") if kind == "price_adj" else total
        elif kind == "gold":
            price = quote_return(windows["GLD"], day, "close")
            total = quote_return(windows["GLD"], day, "adj")
            if row["Quality Flag"] != asset.expected_flag:
                fail(stem, f"gold has an unexpected observed-source flag on {day}")
        elif kind == "global_bond":
            if day not in windows["BND"] or day not in windows["BWX"]:
                fail(stem, f"missing bond blend observation on {day}")
            total = 0.45 * quote_return(windows["BND"], day, "adj") + 0.55 * quote_return(windows["BWX"], day, "adj")
            price = total
        elif kind == "global_short_bond":
            if day not in windows["SHY"]:
                fail(stem, f"missing SHY observation on {day}")
            international = [quote_return(windows[symbol], day, "adj") for symbol in ("ISHG", "BWZ")
                             if day in windows[symbol]]
            if not international:
                fail(stem, f"missing international bond observation on {day}")
            weight = float(metadata["us_gdp_weight_last"]["weight"])
            total = weight * quote_return(windows["SHY"], day, "adj") + (1 - weight) * sum(international) / len(international)
            previous = rows[rows.index(row) - 1]["Date"]
            elapsed = (date.fromisoformat(day) - date.fromisoformat(previous)).days
            fee = float(Decimal("0.0026")) * elapsed / 365
            price = (1 + total) / (1 - fee) - 1
        elif kind == "gold2x":
            total = quote_return(windows["UGL"], day, "adj") if day in windows["UGL"] else 0.0
            price = total
        if total is None:
            fail(stem, f"no current source comparison for {day}")
        if abs(float(row["Total Return"]) - total) > 2e-8:
            fail(stem, f"total return disagrees with current source on {day}")
        if price is not None and abs(float(row["Price Return"]) - price) > 2e-8:
            fail(stem, f"price return disagrees with current source on {day}")


def check_parquet(root: Path, stem: str, rows: list[dict[str, str]]) -> None:
    path = root / "data" / "processed" / f"{stem}.parquet"
    if not path.is_file():
        fail(stem, "missing Parquet file")
    frame = pd.read_parquet(path)
    if list(frame.columns) != OUTPUT_COLUMNS or len(frame) != len(rows):
        fail(stem, "CSV/Parquet schema or row count differs")
    parquet_dates = pd.to_datetime(frame["Date"]).dt.strftime("%Y-%m-%d").tolist()
    if parquet_dates != [row["Date"] for row in rows]:
        fail(stem, "CSV/Parquet dates differ")
    for field in NUMERIC:
        values = pd.to_numeric(frame[field], errors="coerce").tolist()
        for index, (row, actual) in enumerate(zip(rows, values)):
            expected = float(row[field]) if row[field] else float("nan")
            if math.isnan(expected) and pd.isna(actual):
                continue
            if not math.isfinite(expected) or not math.isfinite(actual) or not math.isclose(
                expected, actual, rel_tol=1e-12, abs_tol=1e-9
            ):
                fail(stem, f"CSV/Parquet {field} differs on {row['Date']} (row {index})")
    for field in TEXT:
        for row, actual in zip(rows, frame[field].fillna("")):
            if row[field] != actual:
                fail(stem, f"CSV/Parquet {field} differs on {row['Date']}")


def check_arithmetic(stem: str, rows: list[dict[str, str]]) -> None:
    for index, row in enumerate(rows):
        for field in ("Close", "Adj Close"):
            level = float(row[field])
            if not math.isfinite(level) or level <= 0:
                fail(stem, f"invalid {field} on {row['Date']}")
        if index == 0:
            continue
        previous = rows[index - 1]
        for level_field, return_field in (("Close", "Price Return"), ("Adj Close", "Total Return")):
            if not row[return_field]:
                fail(stem, f"missing {return_field} on {row['Date']}")
            expected = float(row[level_field]) / float(previous[level_field]) - 1
            actual = float(row[return_field])
            if not math.isfinite(actual) or not math.isclose(actual, expected, rel_tol=0, abs_tol=2e-8):
                fail(stem, f"invalid {return_field} on {row['Date']}: {actual} vs {expected}")


def check_one(root: Path, ref: str, stem: str, end: date) -> str:
    relative = f"data/processed/{stem}.csv"
    baseline_result = subprocess.run(["git", "show", f"{ref}:{relative}"], cwd=root,
                                     capture_output=True, text=True, check=True)
    baseline = read_csv(baseline_result.stdout, stem)
    path = root / relative
    candidate = read_csv(path.read_text(encoding="utf-8"), stem)
    old_by = {row["Date"]: row for row in baseline}
    new_by = {row["Date"]: row for row in candidate}
    if candidate[0]["Date"] != baseline[0]["Date"]:
        fail(stem, "first historical date changed")
    deleted = old_by.keys() - new_by.keys()
    if deleted:
        fail(stem, f"deleted committed dates: {sorted(deleted)[:3]}")
    allowance = 93 if stem == "cpi_inflation" else 21
    cutoff = date.fromisoformat(baseline[-1]["Date"]).toordinal() - allowance
    changed = [day for day in old_by if old_by[day] != new_by[day]]
    inserted = [day for day in new_by if day not in old_by]
    if any(date.fromisoformat(day).toordinal() < cutoff for day in changed + inserted):
        fail(stem, "committed history changed before permitted recent window")
    if candidate[-1]["Date"] > end.isoformat():
        fail(stem, "candidate extends beyond requested end date")
    age = (end - date.fromisoformat(candidate[-1]["Date"])).days
    if age > (0 if stem == "cpi_inflation" else 5):
        fail(stem, f"output is stale ({candidate[-1]['Date']}; target {end})")
    check_arithmetic(stem, candidate)
    check_parquet(root, stem, candidate)
    metadata_path = root / "sources" / "manifests" / f"{stem}_build.json"
    metadata = json.loads(metadata_path.read_text(encoding="utf-8"))
    sha = hashlib.sha256(path.read_bytes()).hexdigest()
    if (metadata.get("row_count") != len(candidate) or metadata.get("first_date") != candidate[0]["Date"]
            or metadata.get("last_date") != candidate[-1]["Date"] or metadata.get("csv_sha256") != sha):
        fail(stem, "build metadata does not match CSV")
    asset = ASSETS[stem]
    if asset.kind == "cpi":
        raw = root / "sources" / "raw" / "incremental" / "cpi_bls_recent.json"
        if not raw.is_file():
            fail(stem, "missing current BLS response")
        payload = json.loads(raw.read_text(encoding="utf-8"))
        if payload.get("status") != "REQUEST_SUCCEEDED":
            fail(stem, "BLS response failed")
        from build_cpi_inflation import parse_bls_monthly
        monthly = parse_bls_monthly([payload])
        latest_monthly = monthly[-1][0]
        if (end - latest_monthly).days > 90 or metadata.get("latest_monthly_observation") != latest_monthly.isoformat():
            fail(stem, "CPI monthly observation is stale or metadata disagrees")
        check_source_tail(stem, candidate, {}, root, metadata, set(changed + inserted), monthly)
    else:
        windows = {symbol: source_record(root, stem, symbol, end) for symbol in asset.symbols}
        source_latest = [max(rows) for rows in windows.values()]
        if (end - date.fromisoformat(min(source_latest))).days > 5:
            fail(stem, "a required current source is stale")
        check_source_tail(stem, candidate, windows, root, metadata, set(changed + inserted))
    return f"| {stem} | {baseline[-1]['Date']} | {candidate[-1]['Date']} | {len(inserted)} | {len(changed)} |"


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=ROOT)
    parser.add_argument("--base-ref", default="HEAD")
    parser.add_argument("--end-date", required=True, type=date.fromisoformat)
    args = parser.parse_args()
    root = args.root.resolve()
    lines = ["| Dataset | Previous last | Candidate last | New rows | Revised rows |",
             "|---|---|---|---:|---:|"]
    for stem in ASSETS:
        lines.append(check_one(root, args.base_ref, stem, args.end_date))
    summary = "\n".join(lines) + "\n"
    print(summary)
    if os.getenv("GITHUB_STEP_SUMMARY"):
        with open(os.environ["GITHUB_STEP_SUMMARY"], "a", encoding="utf-8") as handle:
            handle.write("## Daily dataset diff\n\n" + summary)


if __name__ == "__main__":
    main()
