"""Build the derived 2x daily-reset gold (UGL-like) total-return dataset.

This dataset models a 2x daily-reset leveraged gold fund (ProShares Ultra Gold, ticker UGL)
back to 1970, long before UGL's 2008 inception.

Method:
  * Underlying daily return is taken from the project's GOLDPM dataset
    (``data/processed/gold.csv``, column ``Price Return``), the pure LBMA Gold Price PM spot
    return. GOLDPM's ``Total Return`` now carries GLD's expense drag, so the leveraged fund builds
    on the pure-spot ``Price Return`` and applies its own financing/fee (costs counted once).
  * The synthetic 2x daily-reset return is::

        lev_ret = L * u - (L-1) * financing_daily - expense_daily

    where ``u`` is the underlying daily gold return, ``L`` is the leverage multiple,
    ``financing_daily`` is the borrowing cost on the ``(L-1)`` borrowed exposure, and
    ``expense_daily`` is the fund expense accrual.
  * Financing uses the Yahoo ^IRX 13-week T-bill discount yield plus a borrowing spread,
    accrued actual/360 over the calendar days between trading rows.
  * The expense ratio is accrued actual/365.
  * The synthetic segment runs from 1970-01-02 through and including UGL's first trading day;
    from the next trading day onward the dataset uses observed UGL adjusted-close daily total
    returns (Yahoo). Levels compound continuously across the boundary.

``Close`` and ``Adj Close`` are equal: a synthetic daily-reset leveraged fund has no separate
price index, so the single series is the (total-return) NAV level normalized to 100 on
1970-01-02. ``Price Return`` equals ``Total Return``.

Note on the benchmark: UGL targets 2x the daily performance of the Bloomberg Gold Subindex
(a futures-based gold benchmark). This model uses LBMA PM spot gold as the underlying; the
calibrated borrowing spread absorbs the average futures roll/storage and spot-vs-futures
difference over the UGL live overlap.
"""

from __future__ import annotations

import argparse
import bisect
import csv
import hashlib
import json
from datetime import date, datetime, time, timedelta, timezone
from decimal import Decimal, getcontext
from pathlib import Path
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

import requests

getcontext().prec = 40

ASSET_ID = "gold_2x"
ALIAS = "GOLD2X"
BASE_ASSET_ID = "gold"

ETF_SYMBOL = "UGL"
ETF_FETCH_START = date(2008, 1, 1)
IRX_SYMBOL = "^IRX"

START_DATE = date(1970, 1, 1)
MAX_START_LAG_DAYS = 7

# Model parameters (see methodology_gold2x.md). The borrowing spread is calibrated against the
# UGL live overlap so synthetic cumulative growth matches observed UGL.
LEVERAGE = Decimal("2")
EXPENSE_RATIO = Decimal("0.0095")      # ProShares UGL annual expense ratio (0.95%).
BORROW_SPREAD = Decimal("0.0093")      # Borrowing spread over ^IRX, annual.
                                       # Calibrated so synthetic cumulative growth matches observed
                                       # UGL over its overlap (ratio ~1.0). Larger than the Treasury
                                       # spreads because it also absorbs gold futures roll/storage
                                       # (UGL is futures-based; spot ran above it under contango).
FINANCING_DAY_COUNT = Decimal("360")   # Money-market actual/360 for financing accrual.
EXPENSE_DAY_COUNT = Decimal("365")     # Actual/365 for expense accrual.

YAHOO_COLUMNS = ["Date", "Open", "High", "Low", "Close", "Adj Close", "Volume"]
PROJECT_COLUMNS = ["Price Return", "Total Return", "Source", "Quality Flag", "Source Notes"]
OUTPUT_COLUMNS = YAHOO_COLUMNS + PROJECT_COLUMNS

SYNTH_FLAG = "model_2x_daily_reset_synthetic_from_goldpm_spot_price_return_minus_financing_and_fee"
ETF_FLAG = "observed_ugl_etf_adjusted_total_return"
HOLIDAY_FLAG = "observed_ugl_us_holiday_flat"

SYNTH_SOURCE = "Derived 2x daily-reset model (GOLDPM spot price return; ^IRX+spread financing; ProShares-style fee)"
ETF_SOURCE = "Yahoo Finance chart API (UGL adjusted-close total return)"
HOLIDAY_SOURCE = "UGL not trading (LBMA-open / US-market-closed holiday); NAV held flat"
SYNTH_NOTES = (
    "Synthetic 2x daily-reset gold total-return NAV: lev_ret = 2*GOLDPM_spot_price_return "
    "- 1*(^IRX/100)*days/360 - 0.0095*days/365. Uses GOLDPM Price Return (pure spot) so fund fees "
    "are applied once. Close == Adj Close. Model-derived, not observed UGL history."
)
ETF_NOTES = "Observed UGL ETF adjusted-close daily total return. Close == Adj Close (normalized 2x NAV level)."
HOLIDAY_NOTES = (
    "LBMA open but US market closed: UGL did not trade. NAV held flat (Total Return 0). The 2x gold "
    "move over the holiday is captured at UGL's next close, against the most recent UGL close (no double-count)."
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


def _exchange_tz(meta: dict):
    timezone_name = meta.get("exchangeTimezoneName", "America/New_York")
    try:
        return ZoneInfo(timezone_name)
    except ZoneInfoNotFoundError:
        return timezone(timedelta(seconds=int(meta.get("gmtoffset", 0))))


def close_series(payload: dict, field: str = "close") -> dict[str, float]:
    """Return {date: value} from a Yahoo chart payload (close or adjclose)."""
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


def round_decimal(value: Decimal) -> str:
    return f"{value:.10f}".rstrip("0").rstrip(".")


def load_base_price_returns(base_csv: Path) -> list[tuple[str, Decimal | None]]:
    """Return [(date, price_return_or_None)] in date order from the base dataset.

    Uses GOLDPM's ``Price Return`` (pure spot, derived from ``Close``) rather than ``Total Return``.
    GOLDPM's ``Total Return`` now carries GLD's expense drag; the leveraged fund must build on the
    pure-spot price return and apply its own financing/fee so costs are not double-counted.
    """
    if not base_csv.exists():
        raise RuntimeError(f"Base dataset not found: {base_csv}. Build {BASE_ASSET_ID} first.")
    rows: list[tuple[str, Decimal | None]] = []
    with base_csv.open(newline="", encoding="utf-8") as handle:
        for row in csv.DictReader(handle):
            pr = row["Price Return"].strip()
            rows.append((row["Date"], Decimal(pr) if pr else None))
    rows.sort(key=lambda item: item[0])
    return rows


def make_irx_lookup(irx_payload: dict):
    irx = close_series(irx_payload, "close")
    irx_sorted = sorted(irx)

    def get_rate(day: str) -> float:
        if day in irx:
            return irx[day]
        idx = bisect.bisect_right(irx_sorted, day) - 1
        return irx[irx_sorted[idx]] if idx >= 0 else 0.0

    return get_rate


def build_rows(
    base_returns: list[tuple[str, Decimal | None]],
    irx_payload: dict,
    etf_adj: dict[str, float],
) -> tuple[list[dict[str, str]], dict]:
    get_irx = make_irx_lookup(irx_payload)

    etf_dates = sorted(etf_adj)
    if not etf_dates:
        raise RuntimeError(f"No {ETF_SYMBOL} data fetched; cannot build observed segment.")
    etf_inception = etf_dates[0]

    base_dates = [d for d, _ in base_returns]
    base_tr = dict(base_returns)

    rows: list[dict[str, str]] = []
    level = Decimal("100")
    previous_date: date | None = None
    model_overlap: list[float] = []
    etf_overlap: list[float] = []
    prev_etf_adj: float | None = None

    for current in base_dates:
        current_date = date.fromisoformat(current)
        is_observed = current > etf_inception

        if previous_date is None:
            rows.append(_row(current, level, "", SYNTH_FLAG, SYNTH_SOURCE, SYNTH_NOTES, ""))
            previous_date = current_date
            prev_etf_adj = etf_adj.get(current)
            continue

        delta_days = Decimal((current_date - previous_date).days)

        if is_observed:
            adj = etf_adj.get(current)
            if adj is None or prev_etf_adj is None:
                # LBMA open but UGL did not trade (US-market holiday). Hold NAV flat instead of
                # compounding a synthetic day: the holiday's gold move is already contained in
                # UGL's next close-to-close return (computed against the most recent UGL close),
                # so inserting a synthetic fill here would double-count it.
                lev_ret = Decimal("0")
                flag, source, notes = HOLIDAY_FLAG, HOLIDAY_SOURCE, HOLIDAY_NOTES
            else:
                lev_ret = Decimal(str(adj)) / Decimal(str(prev_etf_adj)) - Decimal("1")
                flag, source, notes = ETF_FLAG, ETF_SOURCE, ETF_NOTES
        else:
            lev_ret = _synthetic_return(base_tr.get(current), get_irx(current), delta_days)
            flag, source, notes = SYNTH_FLAG, SYNTH_SOURCE, SYNTH_NOTES

        if lev_ret <= Decimal("-1"):
            lev_ret = Decimal("-0.9999")

        level *= Decimal("1") + lev_ret
        rows.append(_row(current, level, lev_ret, flag, source, notes, lev_ret))

        u = base_tr.get(current)
        adj = etf_adj.get(current)
        if current >= etf_inception and u is not None and adj is not None and prev_etf_adj is not None:
            model_ret = _synthetic_return(u, get_irx(current), delta_days)
            model_overlap.append(float(model_ret))
            etf_overlap.append(adj / prev_etf_adj - 1.0)

        previous_date = current_date
        if current in etf_adj:
            prev_etf_adj = etf_adj.get(current)

    calibration = _calibration_stats(model_overlap, etf_overlap)
    calibration["etf_inception"] = etf_inception
    return rows, calibration


def _synthetic_return(u: Decimal | None, irx_rate: float, delta_days: Decimal) -> Decimal:
    if u is None:
        u = Decimal("0")
    financing_daily = (Decimal(str(irx_rate)) / Decimal("100") + BORROW_SPREAD) * delta_days / FINANCING_DAY_COUNT
    expense_daily = EXPENSE_RATIO * delta_days / EXPENSE_DAY_COUNT
    return LEVERAGE * u - (LEVERAGE - Decimal("1")) * financing_daily - expense_daily


def _row(day: str, level: Decimal, ret: Decimal | str, flag: str, source: str, notes: str, price_ret: Decimal | str) -> dict[str, str]:
    level_str = round_decimal(level)
    ret_str = round_decimal(ret) if isinstance(ret, Decimal) else ret
    price_str = round_decimal(price_ret) if isinstance(price_ret, Decimal) else price_ret
    return {
        "Date": day,
        "Open": "",
        "High": "",
        "Low": "",
        "Close": level_str,
        "Adj Close": level_str,
        "Volume": "",
        "Price Return": price_str,
        "Total Return": ret_str,
        "Source": source,
        "Quality Flag": flag,
        "Source Notes": notes,
    }


def _calibration_stats(model: list[float], observed: list[float]) -> dict:
    n = len(model)
    if n < 2:
        return {"overlap_days": n}
    mean_m = sum(model) / n
    mean_o = sum(observed) / n
    cov = sum((m - mean_m) * (o - mean_o) for m, o in zip(model, observed))
    var_m = sum((m - mean_m) ** 2 for m in model)
    var_o = sum((o - mean_o) ** 2 for o in observed)
    corr = cov / (var_m**0.5 * var_o**0.5) if var_m > 0 and var_o > 0 else None
    diffs = [m - o for m, o in zip(model, observed)]
    mean_diff = sum(diffs) / n
    tracking_var = sum((d - mean_diff) ** 2 for d in diffs) / (n - 1)
    daily_te = tracking_var**0.5
    cum_model = 1.0
    cum_obs = 1.0
    for m, o in zip(model, observed):
        cum_model *= 1 + m
        cum_obs *= 1 + o
    return {
        "overlap_days": n,
        "daily_return_correlation": corr,
        "annualized_tracking_error": daily_te * (252**0.5),
        "mean_daily_return_diff": mean_diff,
        "cumulative_model_growth": cum_model,
        "cumulative_etf_growth": cum_obs,
        "cumulative_ratio_model_over_etf": cum_model / cum_obs if cum_obs else None,
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


def write_build_metadata(path: Path, rows: list[dict[str, str]], csv_path: Path, parquet_written: bool, calibration: dict) -> None:
    synth = sum(1 for r in rows if r["Quality Flag"] == SYNTH_FLAG)
    observed = sum(1 for r in rows if r["Quality Flag"] == ETF_FLAG)
    holiday = sum(1 for r in rows if r["Quality Flag"] == HOLIDAY_FLAG)
    metadata = {
        "asset_id": ASSET_ID,
        "alias": ALIAS,
        "base_asset_id": BASE_ASSET_ID,
        "base_return_column": "Price Return",
        "leverage": float(LEVERAGE),
        "expense_ratio": float(EXPENSE_RATIO),
        "borrow_spread": float(BORROW_SPREAD),
        "financing_benchmark": IRX_SYMBOL,
        "observed_etf": ETF_SYMBOL,
        "build_timestamp_utc": datetime.now(timezone.utc).isoformat(),
        "row_count": len(rows),
        "first_date": rows[0]["Date"] if rows else None,
        "last_date": rows[-1]["Date"] if rows else None,
        "synthetic_rows": synth,
        "observed_etf_rows": observed,
        "us_holiday_flat_rows": holiday,
        "csv_path": csv_path.relative_to(path.parent.parent.parent).as_posix(),
        "csv_sha256": checksum(csv_path),
        "parquet_written": parquet_written,
        "quality_flags": sorted({row["Quality Flag"] for row in rows}),
        "calibration_vs_etf_overlap": calibration,
        "notes": SYNTH_NOTES,
    }
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(metadata, indent=2, default=str) + "\n", encoding="utf-8")


def main() -> None:
    args = parse_args()
    root = Path(args.root)
    end_date = date.fromisoformat(args.end_date)
    raw_dir = root / "sources" / "raw"
    raw_dir.mkdir(parents=True, exist_ok=True)

    base_csv = root / "data" / "processed" / f"{BASE_ASSET_ID}.csv"
    base_returns = load_base_price_returns(base_csv)

    print(f"Fetching {IRX_SYMBOL} ...")
    irx_payload = fetch_chart(IRX_SYMBOL, end_date, start_date=START_DATE)
    print(f"Fetching {ETF_SYMBOL} ...")
    etf_payload = fetch_chart(ETF_SYMBOL, end_date, start_date=ETF_FETCH_START)

    (raw_dir / f"{ASSET_ID}_yahoo_irx_chart.json").write_text(json.dumps(irx_payload), encoding="utf-8")
    (raw_dir / f"{ASSET_ID}_yahoo_ugl_chart.json").write_text(json.dumps(etf_payload), encoding="utf-8")

    etf_adj = close_series(etf_payload, "adjclose")
    rows, calibration = build_rows(base_returns, irx_payload, etf_adj)

    if not rows:
        raise RuntimeError("No rows produced.")
    first_date = date.fromisoformat(rows[0]["Date"])
    if first_date < START_DATE or first_date > START_DATE + timedelta(days=MAX_START_LAG_DAYS):
        raise RuntimeError(f"Dataset starts at {rows[0]['Date']}; expected near {START_DATE.isoformat()}")

    interim_csv = root / "data" / "interim" / f"{ASSET_ID}.csv"
    processed_csv = root / "data" / "processed" / f"{ASSET_ID}.csv"
    processed_parquet = root / "data" / "processed" / f"{ASSET_ID}.parquet"

    write_csv(interim_csv, rows)
    write_csv(processed_csv, rows)
    parquet_written = write_parquet_if_available(processed_csv, processed_parquet)
    write_build_metadata(
        root / "sources" / "manifests" / f"{ASSET_ID}_build.json", rows, processed_csv, parquet_written, calibration
    )

    synth = sum(1 for r in rows if r["Quality Flag"] == SYNTH_FLAG)
    observed = sum(1 for r in rows if r["Quality Flag"] == ETF_FLAG)
    holiday = sum(1 for r in rows if r["Quality Flag"] == HOLIDAY_FLAG)
    print(f"Wrote {len(rows)} rows to {processed_csv}")
    print(f"  First: {rows[0]['Date']}  Last: {rows[-1]['Date']}")
    print(f"  Synthetic rows: {synth}  Observed {ETF_SYMBOL} rows: {observed}  US-holiday flat: {holiday}  (inception {calibration.get('etf_inception')})")
    print(f"  Calibration vs {ETF_SYMBOL} overlap: {json.dumps(calibration, default=str)}")
    print(f"  Parquet written: {parquet_written}")


if __name__ == "__main__":
    main()
