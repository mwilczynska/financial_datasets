"""Build the Yahoo-compatible daily Gold dataset.

This dataset is designed to track the SPDR Gold Shares ETF (``GLD``) — including its
fee/expense drag — extended back to 1970, long before GLD's 2004 inception.

Columns:
  * ``Close`` is the LBMA Gold Price PM spot fixing in USD per troy ounce. It is the
    recognizable *price* of gold and is kept pure (no fees) across the whole 1970->now
    history. ``Price Return`` is the daily return of ``Close`` and is therefore the pure
    spot return. (The leveraged derivative ``gold_2x`` uses this pure-spot ``Price Return``
    as its 1x base so that fund fees are applied exactly once.)
  * ``Adj Close`` is a GLD-tracking total-return index:
        - 1970-01-02 -> GLD inception : pure spot return minus GLD's expense drag
          (``GLD_EXPENSE_RATIO`` per year, accrued actual/365). This models what GLD would
          have returned had it existed.
        - From GLD inception onward    : observed GLD adjusted-close daily returns (Yahoo).
          ``Adj Close`` is exactly proportional to GLD's adjusted close in this segment, so
          the modern era *is* GLD. On LBMA-open / US-market-closed holidays GLD does not
          trade; those rows carry ``Adj Close`` forward (flat, Total Return 0) so the
          holiday's gold move is captured once, at GLD's next close, with no double-count.
    ``Total Return`` is the daily return of ``Adj Close``.

Because ``Adj Close`` carries GLD's fee drag, it diverges below ``Close`` over time; the two
are no longer equal.
"""

from __future__ import annotations

import argparse
import bisect
import csv
import hashlib
import json
from datetime import date, datetime, time, timedelta, timezone
from pathlib import Path

import requests


ASSET_ID = "gold"
ASSET_NAME = "Gold (GLD-tracking, LBMA PM spot extended)"
LBMA_GOLD_PM_URL = "https://prices.lbma.org.uk/json/gold_pm.json"

ETF_SYMBOL = "GLD"
ETF_FETCH_START = date(2004, 1, 1)
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
ETF_SOURCE = "LBMA Gold Price PM spot (price) + Yahoo GLD adjusted close (total return)"
ETF_FLAG = "observed_gld_etf_adjusted_total_return"
ETF_NOTES = (
    "Close = LBMA Gold Price PM USD/oz (pure spot). Adj Close tracks observed SPDR Gold Shares "
    "(GLD) adjusted-close total return. On GLD's (NYSE) trading calendar so it aligns with GLD "
    "day-for-day in return-based backtests."
)
# NYSE-open / LBMA-closed days (UK bank holidays): GLD trades but there is no LBMA fix. Adj Close
# still follows GLD; Close carries the most recent LBMA fix forward so the series stays on GLD's
# calendar without inventing a spot fixing.
ETF_FFILL_FLAG = "observed_gld_us_open_lbma_holiday_close_gld_step"
ETF_FFILL_SOURCE = "GLD-stepped spot (no LBMA fix) + Yahoo GLD adjusted close"
ETF_FFILL_NOTES = (
    "NYSE open but LBMA closed (UK bank holiday): no LBMA fix. Adj Close tracks observed GLD; Close "
    "is stepped by GLD's move from the prior row (telescopes back to the next LBMA fix)."
)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--end-date", default=date.today().isoformat(), help="Inclusive end date, YYYY-MM-DD.")
    parser.add_argument("--root", default=".", help="Project root.")
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


def adjclose_series(payload: dict) -> dict[str, float]:
    """Return {date_iso: adjusted_close} from a Yahoo chart payload (UTC date keys)."""
    result = payload["chart"]["result"][0]
    timestamps = result.get("timestamp") or []
    adjclose = result.get("indicators", {}).get("adjclose", [{}])[0].get("adjclose", [])
    values: dict[str, float] = {}
    for index, timestamp in enumerate(timestamps):
        value = adjclose[index] if index < len(adjclose) else None
        if value is None:
            continue
        day = datetime.fromtimestamp(timestamp, timezone.utc).date().isoformat()
        values[day] = float(value)
    return values


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


def build_rows(payload: list[dict], gld_adj: dict[str, float], end_date: date) -> list[dict[str, str]]:
    """Build rows: Close = LBMA PM spot; Adj Close = GLD-tracking total-return index.

    Two phases on two calendars:
      * Model (1970 -> GLD inception): LBMA (London) trading calendar; Adj Close = spot return minus
        GLD expense drag.
      * Observed (GLD inception -> present): GLD's (NYSE) trading calendar; Adj Close is GLD rescaled
        so the dataset aligns with GLD day-for-day. This is essential for return-based backtests: a
        London-calendar series compared against a US-calendar ETF by intersecting daily returns
        drifts on every UK-bank-holiday day (GLD trades, LBMA closed) even though the levels match.
    """
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
    lbma_by_iso = {iso: c for _, iso, c in lbma}
    lbma_isos = [iso for _, iso, _ in lbma]  # sorted, for ffill lookup

    gld_isos = sorted(d for d in gld_adj if date.fromisoformat(d) <= end_date)
    gld_inception = gld_isos[0] if gld_isos else None

    rows: list[dict[str, str]] = []
    previous_close: float | None = None
    previous_day: date | None = None
    adj_level: float | None = None

    # --- Phase 1: model era on the LBMA calendar (dates strictly before GLD inception) ---
    for row_date, iso, close in lbma:
        if gld_inception is not None and iso >= gld_inception:
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

    if gld_inception is None:
        return rows  # offline / no GLD: model-only fallback

    # --- Phase 2: observed era on GLD's (NYSE) calendar (GLD inception onward) ---
    # Continuity: anchor the GLD level to the running index at the splice.
    base_level = adj_level if adj_level is not None else lbma_by_iso.get(gld_inception, gld_adj[gld_inception])
    gld_scale = base_level / gld_adj[gld_inception]
    prev_gld = gld_adj[gld_inception]
    for iso in gld_isos:
        row_date = date.fromisoformat(iso)
        gld_value = gld_adj[iso]
        if iso in lbma_by_iso:
            close = lbma_by_iso[iso]
            flag, source, notes = ETF_FLAG, ETF_SOURCE, ETF_NOTES
        else:
            # NYSE open, LBMA closed (UK bank holiday): no LBMA fix. Step Close with GLD's move so
            # the spot-price path (and Price Return, which GOLD2X builds on) stays realistic; gold
            # traded globally even though London did not fix. Across the gap this telescopes back to
            # the next LBMA fix, so the running Close stays anchored to the LBMA series.
            if previous_close is not None and prev_gld:
                close = previous_close * (gld_value / prev_gld)
            else:
                idx = bisect.bisect_right(lbma_isos, iso) - 1
                close = lbma_by_iso[lbma_isos[idx]] if idx >= 0 else previous_close
            flag, source, notes = ETF_FFILL_FLAG, ETF_FFILL_SOURCE, ETF_FFILL_NOTES

        new_level = gld_scale * gld_value
        if previous_close is None:
            price_return = ""
            total_return = ""
            adj_level = new_level
        else:
            price_return = round_float(close / previous_close - 1)
            total_return = round_float(new_level / adj_level - 1)
            adj_level = new_level
        rows.append(_emit(iso, close, adj_level, price_return, total_return, flag, source, notes))
        previous_close = close
        previous_day = row_date
        prev_gld = gld_value

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
    model_rows = sum(1 for r in rows if r["Quality Flag"] == MODEL_FLAG)
    etf_rows = sum(1 for r in rows if r["Quality Flag"] == ETF_FLAG)
    ffill_rows = sum(1 for r in rows if r["Quality Flag"] == ETF_FFILL_FLAG)
    metadata = {
        "asset_id": ASSET_ID,
        "asset_name": ASSET_NAME,
        "tracks_etf": ETF_SYMBOL,
        "observed_era_calendar": "NYSE (GLD trading days)",
        "gld_expense_ratio": GLD_EXPENSE_RATIO,
        "source": MODEL_SOURCE,
        "source_url": LBMA_GOLD_PM_URL,
        "etf_source": f"https://query1.finance.yahoo.com/v8/finance/chart/{ETF_SYMBOL}",
        "build_timestamp_utc": datetime.now(timezone.utc).isoformat(),
        "row_count": len(rows),
        "first_date": rows[0]["Date"] if rows else None,
        "last_date": rows[-1]["Date"] if rows else None,
        "model_rows": model_rows,
        "observed_gld_rows": etf_rows,
        "observed_gld_ffill_close_rows": ffill_rows,
        "csv_path": csv_path.relative_to(path.parent.parent.parent).as_posix(),
        "csv_sha256": checksum(csv_path),
        "parquet_written": parquet_written,
        "quality_flags": sorted({row["Quality Flag"] for row in rows}),
        "notes": MODEL_NOTES,
    }
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(metadata, indent=2) + "\n", encoding="utf-8")


def main() -> None:
    args = parse_args()
    root = Path(args.root)
    end_date = date.fromisoformat(args.end_date)

    payload = fetch_lbma_gold_pm()
    raw_path = root / "sources" / "raw" / f"{ASSET_ID}_lbma_gold_pm.json"
    raw_path.parent.mkdir(parents=True, exist_ok=True)
    raw_path.write_text(json.dumps(payload), encoding="utf-8")

    print(f"Fetching {ETF_SYMBOL} ...")
    gld_payload = fetch_chart(ETF_SYMBOL, end_date, start_date=ETF_FETCH_START)
    (raw_path.parent / f"{ASSET_ID}_yahoo_gld_chart.json").write_text(json.dumps(gld_payload), encoding="utf-8")
    gld_adj = adjclose_series(gld_payload)

    rows = build_rows(payload, gld_adj, end_date)
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
    write_build_metadata(root / "sources" / "manifests" / f"{ASSET_ID}_build.json", rows, processed_csv, parquet_written)

    model_rows = sum(1 for r in rows if r["Quality Flag"] == MODEL_FLAG)
    etf_rows = sum(1 for r in rows if r["Quality Flag"] == ETF_FLAG)
    ffill_rows = sum(1 for r in rows if r["Quality Flag"] == ETF_FFILL_FLAG)
    print(f"Wrote {len(rows)} rows to {processed_csv}")
    print(f"  First: {rows[0]['Date']}  Last: {rows[-1]['Date']}")
    print(f"  Model rows: {model_rows}  Observed GLD rows: {etf_rows}  (NYSE cal; ffill-close UK-holiday rows: {ffill_rows})")
    if parquet_written:
        print(f"Wrote Parquet to {processed_parquet}")
    else:
        print("Parquet not written because pandas/pyarrow is unavailable")


if __name__ == "__main__":
    main()
