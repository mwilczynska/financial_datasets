"""Build observed GLD price and adjusted indices from its first quote, 2004-11-18.

Before GLD, Close is published historical LBMA PM spot and Adj Close models
GLD's expense drag. Both observed columns are scaled GLD indices, not USD/oz.
Ordinary rebuilds preserve the pre-GLD model and retrieve only GLD. Re-fetching
historical LBMA is an explicit optional action.
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import math
from datetime import date, datetime, time, timedelta, timezone
from pathlib import Path

import requests


ASSET_ID = "gold"
ASSET_NAME = "Gold (GLD price and total return, modeled history to 1970)"
LBMA_GOLD_PM_URL = "https://prices.lbma.org.uk/json/gold_pm.json"

ETF_SYMBOL = "GLD"
ETF_FETCH_START = date(2004, 1, 1)
ETF_FIRST_DATE = "2004-11-18"
# SPDR Gold Shares annual expense ratio (0.40%). Used to model GLD's fee drag before GLD
# existed. The observed GLD-vs-spot underperformance over the live overlap (~0.42%/yr)
# corroborates this value.
GLD_EXPENSE_RATIO = 0.0040
EXPENSE_DAY_COUNT = 365.0

START_DATE = date(1970, 1, 1)
MAX_START_LAG_DAYS = 7
YAHOO_COLUMNS = ["Date", "Open", "High", "Low", "Close", "Adj Close", "Volume"]
PROJECT_COLUMNS = ["Price Return", "Total Return", "Source", "Quality Flag", "Source Notes"]
OUTPUT_COLUMNS = YAHOO_COLUMNS + PROJECT_COLUMNS

MODEL_SOURCE = "LBMA Gold Price PM spot (price) minus GLD expense drag (total return)"
MODEL_FLAG = "model_gld_tracking_lbma_pm_spot_minus_gld_expense"
MODEL_NOTES = (
    "Close = LBMA Gold Price PM USD/oz (pure spot). Adj Close = spot total return minus "
    f"GLD expense drag ({GLD_EXPENSE_RATIO:.4f}/yr, actual/365); models GLD before its 2004 inception. "
    "LBMA (London) trading calendar."
)
ETF_SOURCE = "Yahoo Finance chart API (GLD close and adjusted close)"
ETF_FLAG = "observed_gld_etf_price_and_adjusted_total_return"
ETF_NOTES = (
    "Close = continuously scaled GLD market close; Adj Close = continuously scaled GLD adjusted close. "
    "GLD fees are already included. These are index levels, not USD/oz spot quotes. "
    "NYSE (GLD) calendar from 2004-11-18; first GLD observation anchors both indices "
    "to the prior modeled levels with zero splice return."
)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--end-date", default=date.today().isoformat(), help="Inclusive end date, YYYY-MM-DD.")
    parser.add_argument("--root", default=".", help="Project root.")
    parser.add_argument("--refresh-historical-sources", action="store_true",
                        help="Explicitly retrieve LBMA to rebuild the pre-GLD model.")
    return parser.parse_args()


def fetch_lbma_gold_pm() -> list[dict]:
    response = requests.get(LBMA_GOLD_PM_URL, timeout=60, headers={"User-Agent": "Mozilla/5.0"})
    response.raise_for_status()
    return response.json()


def unix_seconds(day: date) -> int:
    return int(datetime.combine(day, time.min, tzinfo=timezone.utc).timestamp())


def fetch_chart(symbol: str, end_date: date, start_date: date) -> dict:
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


def chart_series(payload: dict) -> tuple[dict[str, float], dict[str, float]]:
    try:
        from .incremental_update import chart_rows
    except ImportError:
        from incremental_update import chart_rows
    result = (payload.get("chart", {}).get("result") or [None])[0]
    if not result or result.get("meta", {}).get("symbol") != ETF_SYMBOL:
        raise RuntimeError("Missing or mismatched GLD chart result")
    quotes = chart_rows(payload)
    return ({d: r["close"] for d, r in quotes.items()}, {d: r["adj"] for d, r in quotes.items()})


def adjclose_series(payload: dict) -> dict[str, float]:
    return chart_series(payload)[1]


def round_float(value: float | None) -> str:
    if value is None:
        return ""
    return f"{float(value):.10f}".rstrip("0").rstrip(".")


def _emit(iso, close, adj_level, price_return, total_return, flag, source, notes) -> dict[str, str]:
    return {
        "Date": iso,
        "Open": "",
        "High": "",
        "Low": "",
        "Close": round_float(close),
        "Adj Close": round_float(adj_level),
        "Volume": "",
        "Price Return": price_return,
        "Total Return": total_return,
        "Source": source,
        "Quality Flag": flag,
        "Source Notes": notes,
    }


def build_rows(payload: list[dict], gld_adj: dict[str, float], end_date: date,
               *, gld_close: dict[str, float]) -> list[dict[str, str]]:
    """Explicit historical rebuild: model LBMA before GLD, then stitch GLD."""
    # Parse the LBMA PM fixings in window.
    lbma: list[tuple[date, str, float]] = []
    for item in payload:
        row_date = date.fromisoformat(item["d"])
        if row_date < START_DATE or row_date > end_date:
            continue
        values = item.get("v") or []
        if not values or values[0] is None:
            continue
        lbma.append((row_date, row_date.isoformat(), float(values[0])))
    lbma.sort(key=lambda x: x[0])

    gld_inception = ETF_FIRST_DATE

    rows: list[dict[str, str]] = []
    previous_close: float | None = None
    previous_day: date | None = None
    adj_level: float | None = None

    # --- Phase 1: model era on the LBMA calendar (dates strictly before GLD inception) ---
    for row_date, iso, close in lbma:
        if iso >= gld_inception:
            break
        if previous_close is None:
            adj_level = close
            price_return = ""
            total_return = ""
        else:
            price_return = round_float(close / previous_close - 1)
            delta_days = (row_date - previous_day).days
            fee_factor = 1.0 - GLD_EXPENSE_RATIO * delta_days / EXPENSE_DAY_COUNT
            new_level = adj_level * (close / previous_close) * fee_factor
            total_return = round_float(new_level / adj_level - 1)
            adj_level = new_level
        rows.append(_emit(iso, close, adj_level, price_return, total_return, MODEL_FLAG, MODEL_SOURCE, MODEL_NOTES))
        previous_close = close
        previous_day = row_date

    return stitch_rows(rows, gld_close, gld_adj, end_date)


def stitch_rows(model_rows: list[dict[str, str]], gld_close: dict[str, float],
                gld_adj: dict[str, float], end_date: date) -> list[dict[str, str]]:
    """Preserve modeled history and join both GLD indices at its first available quote.

    There is no observable cross-instrument return into GLD's first quote; that
    date anchors to the preceding model levels and has zero splice return.
    """
    model_dates = [r["Date"] for r in model_rows]
    if (not model_dates or model_dates != sorted(set(model_dates))
            or model_dates[-1] != "2004-11-17"
            or not START_DATE <= date.fromisoformat(model_dates[0]) <= START_DATE + timedelta(days=MAX_START_LAG_DAYS)):
        raise RuntimeError("Pre-GLD model must cover 1970 through 2004-11-17 with sorted unique dates")
    if any(r["Quality Flag"] != MODEL_FLAG for r in model_rows):
        raise RuntimeError("Unexpected pre-GLD model segment")
    for row in model_rows:
        if any(not math.isfinite(float(row[k])) or float(row[k]) <= 0 for k in ("Close", "Adj Close")):
            raise RuntimeError(f"Invalid model level on {row['Date']}")
    dates = sorted(d for d in gld_close if d <= end_date.isoformat())
    adj_dates = sorted(d for d in gld_adj if d <= end_date.isoformat())
    if not dates or dates != adj_dates or dates[0] != ETF_FIRST_DATE:
        raise RuntimeError("GLD close and adjusted close must start together on 2004-11-18")
    if (end_date - date.fromisoformat(dates[-1])).days > 5:
        raise RuntimeError("GLD history is stale for the requested end date")
    for index, day in enumerate(dates):
        if any(not math.isfinite(v) or v <= 0 for v in (gld_close[day], gld_adj[day])):
            raise RuntimeError(f"Invalid GLD observation on {day}")
        if day != dates[0] and (date.fromisoformat(day) - date.fromisoformat(dates[index - 1])).days > 5:
            raise RuntimeError(f"Gap in GLD history before {day}")
    rows = [dict(row) for row in model_rows]
    price_scale = float(rows[-1]["Close"]) / gld_close[dates[0]]
    adj_scale = float(rows[-1]["Adj Close"]) / gld_adj[dates[0]]
    for day in dates:
        close = float(rows[-1]["Close"]) if day == dates[0] else price_scale * gld_close[day]
        adj = float(rows[-1]["Adj Close"]) if day == dates[0] else adj_scale * gld_adj[day]
        price_return = round_float(close / float(rows[-1]["Close"]) - 1)
        total_return = round_float(adj / float(rows[-1]["Adj Close"]) - 1)
        rows.append(_emit(day, close, adj, price_return, total_return, ETF_FLAG, ETF_SOURCE, ETF_NOTES))
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


def write_build_metadata(path: Path, rows: list[dict[str, str]], csv_path: Path, parquet_written: bool,
                         sources: dict | None = None) -> None:
    model_rows = sum(1 for r in rows if r["Quality Flag"] == MODEL_FLAG)
    etf_rows = sum(1 for r in rows if r["Quality Flag"] == ETF_FLAG)
    metadata = {
        "asset_id": ASSET_ID,
        "asset_name": ASSET_NAME,
        "tracks_etf": ETF_SYMBOL,
        "observed_era_calendar": "NYSE (GLD trading days)",
        "gld_expense_ratio": GLD_EXPENSE_RATIO,
        "source": "Published pre-GLD model + Yahoo GLD close and adjusted close",
        "source_url": f"https://query1.finance.yahoo.com/v8/finance/chart/{ETF_SYMBOL}",
        "gld_first_observation": ETF_FIRST_DATE,
        "price_definition": "historical spot then scaled GLD market-close index",
        "splice": {"last_model_date": "2004-11-17", "first_gld_date": ETF_FIRST_DATE,
                   "first_gld_return": "zero; first quote anchors both indices to prior modeled levels"},
        "build_sources": sources or {},
        "etf_source": f"https://query1.finance.yahoo.com/v8/finance/chart/{ETF_SYMBOL}",
        "build_timestamp_utc": datetime.now(timezone.utc).isoformat(),
        "row_count": len(rows),
        "first_date": rows[0]["Date"] if rows else None,
        "last_date": rows[-1]["Date"] if rows else None,
        "model_rows": model_rows,
        "observed_gld_rows": etf_rows,
        "csv_path": csv_path.relative_to(path.parent.parent.parent).as_posix(),
        "csv_sha256": checksum(csv_path),
        "parquet_written": parquet_written,
        "quality_flags": sorted({row["Quality Flag"] for row in rows}),
        "notes": ETF_NOTES,
    }
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(metadata, indent=2) + "\n", encoding="utf-8")


def main() -> None:
    args = parse_args()
    root = Path(args.root)
    end_date = date.fromisoformat(args.end_date)

    raw_path = root / "sources" / "raw" / f"{ASSET_ID}_lbma_gold_pm.json"
    raw_path.parent.mkdir(parents=True, exist_ok=True)
    baseline_path = root / "data/processed/gold.csv"
    if args.refresh_historical_sources:
        payload = fetch_lbma_gold_pm()
        raw_path.write_text(json.dumps(payload), encoding="utf-8")
        history_source = {"url": LBMA_GOLD_PM_URL, "sha256": checksum(raw_path), "mode": "explicit_historical_refresh"}
    else:
        with baseline_path.open(newline="", encoding="utf-8") as handle:
            model = [r for r in csv.DictReader(handle) if r["Date"] < ETF_FIRST_DATE]
        history_source = {"path": "data/processed/gold.csv", "mode": "preserved_published_model",
                          "model_rows_sha256": hashlib.sha256(json.dumps(model, sort_keys=True).encode()).hexdigest()}

    print(f"Fetching {ETF_SYMBOL} ...")
    gld_payload = fetch_chart(ETF_SYMBOL, end_date, start_date=ETF_FETCH_START)
    (raw_path.parent / f"{ASSET_ID}_yahoo_gld_chart.json").write_text(json.dumps(gld_payload), encoding="utf-8")
    gld_close, gld_adj = chart_series(gld_payload)

    rows = (build_rows(payload, gld_adj, end_date, gld_close=gld_close) if args.refresh_historical_sources
            else stitch_rows(model, gld_close, gld_adj, end_date))
    if not rows:
        raise RuntimeError("No rows returned from LBMA Gold PM payload")

    first_date = date.fromisoformat(rows[0]["Date"])
    if first_date < START_DATE or (first_date - START_DATE).days > MAX_START_LAG_DAYS:
        raise RuntimeError(
            f"Dataset starts at {rows[0]['Date']}; expected first observation near {START_DATE.isoformat()}"
        )

    interim_csv = root / "data" / "interim" / f"{ASSET_ID}.csv"
    processed_csv = root / "data" / "processed" / f"{ASSET_ID}.csv"
    processed_parquet = root / "data" / "processed" / f"{ASSET_ID}.parquet"

    write_csv(interim_csv, rows)
    write_csv(processed_csv, rows)
    parquet_written = write_parquet_if_available(processed_csv, processed_parquet)
    sources = {"historical_model": history_source, "GLD": {
        "url": "https://query1.finance.yahoo.com/v8/finance/chart/GLD",
        "path": "sources/raw/gold_yahoo_gld_chart.json", "sha256": checksum(raw_path.parent / "gold_yahoo_gld_chart.json"),
        "accessed_utc": datetime.now(timezone.utc).isoformat(), "first_date": min(gld_close), "last_date": max(gld_close)}}
    write_build_metadata(root / "sources" / "manifests" / f"{ASSET_ID}_build.json", rows, processed_csv, parquet_written, sources)

    model_rows = sum(1 for r in rows if r["Quality Flag"] == MODEL_FLAG)
    etf_rows = sum(1 for r in rows if r["Quality Flag"] == ETF_FLAG)
    print(f"Wrote {len(rows)} rows to {processed_csv}")
    print(f"  First: {rows[0]['Date']}  Last: {rows[-1]['Date']}")
    print(f"  Model rows: {model_rows}  Observed GLD rows: {etf_rows}  (NYSE calendar from {ETF_FIRST_DATE})")
    if parquet_written:
        print(f"Wrote Parquet to {processed_parquet}")
    else:
        print("Parquet not written because pandas/pyarrow is unavailable")


if __name__ == "__main__":
    main()
