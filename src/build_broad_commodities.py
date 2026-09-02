"""Build a Yahoo-compatible DBC-like broad commodities total-return dataset.

Source chain (1970-present), all normalized to 100 at 1970-01-02 and compounded
continuously across splices:

  Segment 0 (1970-01-02 .. 1984-01-03): S&P GSCI Total Return anchor, log-linear
      daily smoothing on the ^IRX trading calendar. The anchor is the only
      roll-inclusive, collateralized broad commodity total-return series that
      reaches 1970; daily volatility is smoothed (no free daily broad-commodity
      data exists before 1984), but the LEVEL carries genuine roll yield, T-bill
      collateral and the GSCI production-weighted composition.
  Segment 1 (1984-01-04 .. 1991-01-02): Yahoo ^SPGSCI spot DAILY SHAPE overlaid
      (per anchor interval) onto the S&P GSCI Total Return anchor. This injects
      the roll yield and collateral the spot index omits (~9%/yr roll + ~7%/yr
      T-bill in that era) while preserving real daily spot moves and event timing.
  Segment 2 (1991-01-03 .. 2006-02-06): Yahoo ^BCOM Bloomberg Commodity Excess
      Return (spot + roll) + ^IRX T-bill collateral.
  Segment 3 (2006-02-07 .. present): Yahoo DBC observed total-return ETF.

Column convention:
  Close / Price Return = EXCESS-RETURN level (spot + roll, no collateral).
  Adj Close / Total Return = TOTAL-RETURN level (excess return + T-bill collateral).
  The backtester reads Adj Close.

The S&P GSCI Total Return anchor is a static committed file
(`sources/raw/broad_commodities_gsci_tr_macromicro.csv`); it is historical and
does not change. Only the DBC tail refreshes from Yahoo on update.
"""

from __future__ import annotations

import argparse
import bisect
import csv
import hashlib
import json
import math
from datetime import date, datetime, time, timedelta, timezone
from pathlib import Path
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

import requests


ASSET_ID = "broad_commodities"
ASSET_NAME = "Broad Commodities / DBC-like Total Return"
START_DATE = date(1970, 1, 1)
SPGSCI_START_DATE = date(1984, 1, 1)
SPGSCI_SYMBOL = "^SPGSCI"
BCOM_SYMBOL = "^BCOM"
DBC_SYMBOL = "DBC"
IRX_SYMBOL = "^IRX"
BROAD_MODEL_START = date(1970, 1, 2)
# Static committed S&P GSCI Total Return anchor (base 100 at 1970-01-02).
GSCI_ANCHOR_FILE = "broad_commodities_gsci_tr_macromicro.csv"

SOURCE = (
    "S&P GSCI Total Return anchor (MacroMicro republication of the S&P GSCI Total "
    "Return Index, base 100 at 1970-01-02) for the 1970-1991 reconstruction: "
    "log-linear daily smoothing (Segment 0, 1970-1983) and Yahoo ^SPGSCI spot daily "
    "shape overlaid to the anchor (Segment 1, 1984-1991); "
    "Yahoo Finance chart API ^BCOM Bloomberg Commodity Excess Return + ^IRX T-bill "
    "collateral (Segment 2, 1991-2006); DBC adjusted close total-return ETF "
    "(Segment 3, 2006-present)"
)
YAHOO_COLUMNS = ["Date", "Open", "High", "Low", "Close", "Adj Close", "Volume"]
PROJECT_COLUMNS = ["Price Return", "Total Return", "Source", "Quality Flag", "Source Notes"]
OUTPUT_COLUMNS = YAHOO_COLUMNS + PROJECT_COLUMNS

GSCI_SMOOTHED_FLAG = "model_gsci_total_return_anchor_smoothed_daily"
GSCI_SHAPE_FLAG = "model_gsci_total_return_anchor_with_spgsci_spot_daily_shape"
BCOM_FLAG = "model_bcom_excess_return_plus_tbill_collateral"
DBC_FLAG = "observed_yahoo_dbc_dblci_total_return_etf"

GSCI_SMOOTHED_NOTES = (
    "S&P GSCI TOTAL RETURN ANCHOR, SMOOTHED. Adj Close follows the S&P GSCI Total "
    "Return Index (roll yield + T-bill collateral + GSCI production weights), "
    "republished by MacroMicro at ~bi-monthly resolution and base 100 at 1970-01-02, "
    "log-linearly interpolated to daily ^IRX trading dates. Close strips the daily "
    "^IRX T-bill collateral to give the excess-return (spot+roll) level. No free daily "
    "broad-commodity data exists before 1984, so within-period daily volatility is "
    "SMOOTHED (model-derived), but the level carries genuine roll yield and collateral. "
    "S&P GSCI is back-tested before its 1991 launch."
)
GSCI_SHAPE_NOTES = (
    "S&P GSCI TOTAL RETURN ANCHOR with ^SPGSCI SPOT DAILY SHAPE. Adj Close uses the "
    "daily Yahoo ^SPGSCI spot-index return shape, scaled by a constant per-anchor-interval "
    "overlay so each ~bi-monthly interval compounds to the S&P GSCI Total Return anchor. "
    "This injects the roll yield and T-bill collateral the spot index omits (~9%/yr roll + "
    "~7%/yr collateral in 1984-1991) while preserving genuine daily spot moves and event "
    "timing. Close strips the daily ^IRX collateral to give the excess-return level."
)
BCOM_NOTES = (
    "Bloomberg Commodity Excess Return Index via Yahoo ^BCOM (spot + roll yield; no collateral). "
    "Adj Close adds daily ^IRX T-bill collateral accrual (IRX%/100/365 per day). "
    "Index methodology change from the GSCI Total Return anchor at the 1991 boundary: different "
    "commodity weights and a different index family."
)
DBC_NOTES = (
    "DBC (Invesco DB Commodity Index Tracking Fund / DBLCI) observed ETF. "
    "Close compounds DBC daily close returns; Adj Close compounds DBC daily adjusted-close "
    "returns (Yahoo adj close captures accumulated T-bill collateral distributions). "
    "Index methodology change from BCOM Excess Return + T-bill model at the 2006 boundary. "
    "DBC uses optimum-yield rolling (different from BCOM roll rules). ~0.89% annual expense drag."
)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--end-date", default=date.today().isoformat(), help="Inclusive end date YYYY-MM-DD.")
    parser.add_argument("--root", default=".", help="Project root directory.")
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


def chart_rows(payload: dict) -> list[dict]:
    result = payload["chart"]["result"][0]
    timestamps = result.get("timestamp") or []
    quote = result["indicators"]["quote"][0]
    adjclose_list = result.get("indicators", {}).get("adjclose", [{}])[0].get("adjclose", [])
    meta = result.get("meta", {})
    timezone_name = meta.get("exchangeTimezoneName", "America/New_York")
    try:
        exchange_tz = ZoneInfo(timezone_name)
    except ZoneInfoNotFoundError:
        exchange_tz = timezone(timedelta(seconds=int(meta.get("gmtoffset", 0))))

    rows = []
    for index, timestamp in enumerate(timestamps):
        close = quote.get("close", [None])[index]
        adjusted = adjclose_list[index] if index < len(adjclose_list) else close
        if close is None:
            continue
        if adjusted is None:
            adjusted = close
        rows.append({
            "Date": datetime.fromtimestamp(timestamp, exchange_tz).date().isoformat(),
            "Close": float(close),
            "Adj Close": float(adjusted),
        })
    return rows


def load_gsci_anchor(path: Path) -> list[tuple[str, float]]:
    """Load the S&P GSCI Total Return anchor (Date,GSCI_TR_Index), sorted by date."""
    if not path.exists():
        raise RuntimeError(
            f"S&P GSCI Total Return anchor not found: {path}. This is a static committed "
            "file (MacroMicro republication of the S&P GSCI TR Index); it cannot be refetched "
            "programmatically."
        )
    anchor: list[tuple[str, float]] = []
    with path.open(newline="", encoding="utf-8") as handle:
        for row in csv.DictReader(handle):
            anchor.append((row["Date"], float(row["GSCI_TR_Index"])))
    anchor.sort(key=lambda item: item[0])
    if not anchor or anchor[0][0] != BROAD_MODEL_START.isoformat():
        raise RuntimeError("GSCI anchor must start at 1970-01-02")
    return anchor


def round_float(value: float) -> str:
    return f"{float(value):.10f}".rstrip("0").rstrip(".")


def build_normalized_rows(
    spgsci_raw: list[dict],
    bcom_raw: list[dict],
    dbc_raw: list[dict],
    irx_raw: list[dict],
    gsci_anchor: list[tuple[str, float]],
) -> list[dict[str, str]]:
    spgsci = {row["Date"]: float(row["Close"]) for row in spgsci_raw}
    bcom = {row["Date"]: float(row["Close"]) for row in bcom_raw}
    dbc_close = {row["Date"]: float(row["Close"]) for row in dbc_raw}
    dbc_adj = {row["Date"]: float(row["Adj Close"]) for row in dbc_raw}
    # IRX close is the annualized T-bill rate in percent (e.g., 5.25 = 5.25% per year)
    irx = {row["Date"]: float(row["Close"]) for row in irx_raw if row.get("Close")}
    irx_sorted = sorted(irx)

    def get_irx_rate(day: str) -> float:
        """Return the IRX rate for the given day with forward-fill for missing dates."""
        if day in irx:
            return irx[day]
        idx = bisect.bisect_right(irx_sorted, day) - 1
        return irx[irx_sorted[idx]] if idx >= 0 else 5.0

    def daily_collateral(day: str) -> float:
        """One-day T-bill collateral growth factor (actual/365)."""
        return 1.0 + get_irx_rate(day) / 100.0 / 365.0

    # --- Segment boundaries (unchanged) ---------------------------------------
    spgsci_dates = sorted(spgsci)
    if len(spgsci_dates) < 2:
        raise RuntimeError("SPGSCI history too short to splice")
    spgsci_return_start = spgsci_dates[1]

    bcom_dates = sorted(bcom)
    if len(bcom_dates) < 2:
        raise RuntimeError("BCOM history too short to splice")
    bcom_return_start = bcom_dates[1]

    dbc_dates = sorted(dbc_close)
    if len(dbc_dates) < 2:
        raise RuntimeError("DBC history too short to splice")
    dbc_return_start = dbc_dates[1]

    model_start = BROAD_MODEL_START.isoformat()
    seg0 = sorted(d for d in irx_sorted if model_start <= d < spgsci_return_start)
    seg1 = sorted(d for d in spgsci if spgsci_return_start <= d < bcom_return_start)
    seg2 = sorted(d for d in bcom if bcom_return_start <= d < dbc_return_start)
    seg3 = sorted(d for d in dbc_close if d >= dbc_return_start)

    if not seg0:
        raise RuntimeError("No IRX dates for Segment 0")
    if not seg1:
        raise RuntimeError("No SPGSCI dates for Segment 1")

    seg0_set, seg1_set, seg2_set, seg3_set = set(seg0), set(seg1), set(seg2), set(seg3)
    all_dates = sorted(seg0_set | seg1_set | seg2_set | seg3_set)

    # --- GSCI Total Return anchor helpers -------------------------------------
    anchor_ords = [date.fromisoformat(d).toordinal() for d, _ in gsci_anchor]
    anchor_logs = [math.log(v) for _, v in gsci_anchor]

    def anchor_log_level(day: str) -> float:
        """Log-linear interpolation of the GSCI TR anchor (extrapolates flat past ends)."""
        o = date.fromisoformat(day).toordinal()
        if o <= anchor_ords[0]:
            return anchor_logs[0]
        if o >= anchor_ords[-1]:
            return anchor_logs[-1]
        i = bisect.bisect_right(anchor_ords, o) - 1
        o0, o1 = anchor_ords[i], anchor_ords[i + 1]
        frac = (o - o0) / (o1 - o0)
        return anchor_logs[i] + frac * (anchor_logs[i + 1] - anchor_logs[i])

    # Segment 0 (1970-1984): smoothed daily TOTAL return = ratio of interpolated anchor levels.
    seg0_total_return: dict[str, float] = {}
    for prev, day in zip(seg0, seg0[1:]):
        seg0_total_return[day] = math.exp(anchor_log_level(day) - anchor_log_level(prev)) - 1.0

    # Segment 1 (1984-1991): ^SPGSCI spot daily shape, overlaid per anchor interval so each
    # interval compounds to the anchor's total return. spgsci consecutive returns give the shape.
    spgsci_index = {d: i for i, d in enumerate(spgsci_dates)}
    seg1_shape_log: dict[str, float] = {}
    for day in seg1:
        j = spgsci_index[day]
        seg1_shape_log[day] = math.log(spgsci[day] / spgsci[spgsci_dates[j - 1]])

    # Group seg1 days by anchor interval index, then solve the per-interval overlay.
    seg1_by_interval: dict[int, list[str]] = {}
    for day in seg1:
        o = date.fromisoformat(day).toordinal()
        idx = bisect.bisect_right(anchor_ords, o) - 1
        idx = max(0, min(idx, len(anchor_ords) - 2))
        seg1_by_interval.setdefault(idx, []).append(day)

    seg1_total_return: dict[str, float] = {}
    for idx, days in seg1_by_interval.items():
        target_log = anchor_logs[idx + 1] - anchor_logs[idx]
        shape_sum = sum(seg1_shape_log[d] for d in days)
        overlay = (target_log - shape_sum) / len(days)
        for d in days:
            seg1_total_return[d] = math.exp(seg1_shape_log[d] + overlay) - 1.0

    # --- Compound levels across the full timeline -----------------------------
    rows: list[dict[str, str]] = []
    close_index = 100.0
    adj_index = 100.0
    prev_seg: str | None = None
    prev_date: str | None = None

    for day in all_dates:
        if day in seg3_set:
            seg = "DBC"
        elif day in seg2_set:
            seg = "BCOM"
        elif day in seg1_set:
            seg = "GSCI_SHAPE"
        else:
            seg = "GSCI_SMOOTH"

        price_return: float | None = None
        total_return: float | None = None

        if prev_date is not None:
            if seg == "GSCI_SMOOTH":
                total_return = seg0_total_return[day]
                # Strip daily T-bill collateral to recover the excess-return (spot+roll) level.
                price_return = (1 + total_return) / daily_collateral(day) - 1

            elif seg == "GSCI_SHAPE":
                total_return = seg1_total_return[day]
                price_return = (1 + total_return) / daily_collateral(day) - 1

            elif seg == "BCOM" and prev_seg == "BCOM":
                ratio = bcom[day] / bcom[prev_date]
                price_return = ratio - 1
                total_return = ratio * daily_collateral(day) - 1

            elif seg == "BCOM" and prev_seg == "GSCI_SHAPE":
                # Splice GSCI shape -> BCOM. BCOM has an overlap value on prev_date (= bcom_dates[0]).
                prior_bcom = bcom.get(prev_date)
                if prior_bcom is None:
                    raise RuntimeError(f"BCOM missing overlap value on {prev_date} for splice to {day}")
                ratio = bcom[day] / prior_bcom
                price_return = ratio - 1
                total_return = ratio * daily_collateral(day) - 1

            elif seg == "DBC" and prev_seg == "DBC":
                price_return = dbc_close[day] / dbc_close[prev_date] - 1
                total_return = dbc_adj[day] / dbc_adj[prev_date] - 1

            elif seg == "DBC" and prev_seg == "BCOM":
                # Splice BCOM -> DBC. DBC has an overlap value on prev_date (= dbc_dates[0]).
                prior_dbc_close = dbc_close.get(prev_date)
                prior_dbc_adj = dbc_adj.get(prev_date)
                if prior_dbc_close is None or prior_dbc_adj is None:
                    raise RuntimeError(f"DBC missing overlap value on {prev_date} for splice to {day}")
                price_return = dbc_close[day] / prior_dbc_close - 1
                total_return = dbc_adj[day] / prior_dbc_adj - 1

            else:
                raise RuntimeError(f"Unexpected segment transition {prev_seg} -> {seg} on {day}")

            close_index *= 1 + price_return
            adj_index *= 1 + total_return

        if seg == "GSCI_SMOOTH":
            flag, notes = GSCI_SMOOTHED_FLAG, GSCI_SMOOTHED_NOTES
            source_label = "S&P GSCI Total Return anchor (MacroMicro), log-linear daily smoothing"
        elif seg == "GSCI_SHAPE":
            flag, notes = GSCI_SHAPE_FLAG, GSCI_SHAPE_NOTES
            source_label = "Yahoo ^SPGSCI spot daily shape overlaid to S&P GSCI Total Return anchor"
        elif seg == "BCOM":
            flag, notes = BCOM_FLAG, BCOM_NOTES
            source_label = "Yahoo Finance chart API (^BCOM excess return, ^IRX T-bill collateral)"
        else:
            flag, notes = DBC_FLAG, DBC_NOTES
            source_label = "Yahoo Finance chart API (DBC adjusted close)"

        rows.append({
            "Date": day,
            "Open": "",
            "High": "",
            "Low": "",
            "Close": round_float(close_index),
            "Adj Close": round_float(adj_index),
            "Volume": "",
            "Price Return": "" if price_return is None else round_float(price_return),
            "Total Return": "" if total_return is None else round_float(total_return),
            "Source": source_label,
            "Quality Flag": flag,
            "Source Notes": notes,
        })

        prev_seg = seg
        prev_date = day

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
    quality_flags = {row["Quality Flag"] for row in rows}
    seg_counts = {flag: sum(1 for r in rows if r["Quality Flag"] == flag) for flag in quality_flags}
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
        "quality_flags": sorted(quality_flags),
        "segment_row_counts": seg_counts,
        "coverage_note": (
            "Segments 0-1 (1970-01-02 to 1991-01-02) reconstruct broad commodity TOTAL return "
            "from the S&P GSCI Total Return anchor (roll yield + T-bill collateral + GSCI "
            "production weights). Segment 0 (1970-1983) is log-linearly smoothed to daily because "
            "no free daily broad-commodity data exists before 1984; Segment 1 (1984-1991) overlays "
            "the anchor onto the daily ^SPGSCI spot shape for genuine daily moves. Close is the "
            "excess-return (spot+roll) level; Adj Close is the total-return level. S&P GSCI is "
            "back-tested before its 1991 launch."
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

    print(f"Fetching {SPGSCI_SYMBOL} ...")
    spgsci_payload = fetch_chart(SPGSCI_SYMBOL, end_date, start_date=SPGSCI_START_DATE)
    print(f"Fetching {BCOM_SYMBOL} ...")
    bcom_payload = fetch_chart(BCOM_SYMBOL, end_date, start_date=SPGSCI_START_DATE)
    print(f"Fetching {DBC_SYMBOL} ...")
    dbc_payload = fetch_chart(DBC_SYMBOL, end_date, start_date=SPGSCI_START_DATE)
    print(f"Fetching {IRX_SYMBOL} ...")
    irx_payload = fetch_chart(IRX_SYMBOL, end_date, start_date=START_DATE)

    (raw_dir / f"{ASSET_ID}_yahoo_spgsci_chart.json").write_text(json.dumps(spgsci_payload), encoding="utf-8")
    (raw_dir / f"{ASSET_ID}_yahoo_bcom_chart.json").write_text(json.dumps(bcom_payload), encoding="utf-8")
    (raw_dir / f"{ASSET_ID}_yahoo_dbc_chart.json").write_text(json.dumps(dbc_payload), encoding="utf-8")
    (raw_dir / f"{ASSET_ID}_yahoo_irx_chart.json").write_text(json.dumps(irx_payload), encoding="utf-8")

    gsci_anchor = load_gsci_anchor(raw_dir / GSCI_ANCHOR_FILE)

    spgsci_rows = chart_rows(spgsci_payload)
    bcom_rows = chart_rows(bcom_payload)
    dbc_rows = chart_rows(dbc_payload)
    irx_rows = chart_rows(irx_payload)

    print(f"SPGSCI rows: {len(spgsci_rows)}, first: {spgsci_rows[0]['Date']}, last: {spgsci_rows[-1]['Date']}")
    print(f"BCOM rows: {len(bcom_rows)}, first: {bcom_rows[0]['Date']}, last: {bcom_rows[-1]['Date']}")
    print(f"DBC rows: {len(dbc_rows)}, first: {dbc_rows[0]['Date']}, last: {dbc_rows[-1]['Date']}")
    print(f"IRX rows: {len(irx_rows)}, first: {irx_rows[0]['Date']}, last: {irx_rows[-1]['Date']}")
    print(f"GSCI TR anchor points: {len(gsci_anchor)}, {gsci_anchor[0][0]} -> {gsci_anchor[-1][0]}")

    rows = build_normalized_rows(spgsci_rows, bcom_rows, dbc_rows, irx_rows, gsci_anchor)
    if not rows:
        raise RuntimeError("No broad commodities rows generated")

    interim_csv = root / "data" / "interim" / f"{ASSET_ID}.csv"
    processed_csv = root / "data" / "processed" / f"{ASSET_ID}.csv"
    processed_parquet = root / "data" / "processed" / f"{ASSET_ID}.parquet"

    write_csv(interim_csv, rows)
    write_csv(processed_csv, rows)
    parquet_written = write_parquet_if_available(processed_csv, processed_parquet)
    write_build_metadata(root / "sources" / "manifests" / f"{ASSET_ID}_build.json", rows, processed_csv, parquet_written)

    smooth_count = sum(1 for r in rows if r["Quality Flag"] == GSCI_SMOOTHED_FLAG)
    shape_count = sum(1 for r in rows if r["Quality Flag"] == GSCI_SHAPE_FLAG)
    bcom_count = sum(1 for r in rows if r["Quality Flag"] == BCOM_FLAG)
    dbc_count = sum(1 for r in rows if r["Quality Flag"] == DBC_FLAG)

    print(f"\nWrote {len(rows)} rows to {processed_csv}")
    print(f"First date: {rows[0]['Date']}; last date: {rows[-1]['Date']}")
    print(f"Segment counts: GSCI_SMOOTH={smooth_count}, GSCI_SHAPE={shape_count}, BCOM={bcom_count}, DBC={dbc_count}")
    if parquet_written:
        print(f"Wrote Parquet to {processed_parquet}")
    else:
        print("Parquet not written (pandas/pyarrow unavailable)")


if __name__ == "__main__":
    main()
