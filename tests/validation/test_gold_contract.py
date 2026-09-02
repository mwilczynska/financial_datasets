import csv
import json
from datetime import date, datetime, timedelta, timezone
from decimal import Decimal
from pathlib import Path

import pytest


DATASET = Path("data/processed/gold.csv")
PARQUET_DATASET = Path("data/processed/gold.parquet")
RAW_LBMA_PM = Path("sources/raw/gold_lbma_gold_pm.json")
RAW_GLD = Path("sources/raw/gold_yahoo_gld_chart.json")
MANIFEST = Path("sources/manifests/gold.yml")

YAHOO_COLUMNS = ["Date", "Open", "High", "Low", "Close", "Adj Close", "Volume"]
PROJECT_COLUMNS = ["Price Return", "Total Return", "Source", "Quality Flag", "Source Notes"]
MIN_START_DATE = date(1970, 1, 1)
MAX_START_LAG_DAYS = 7
RETURN_TOLERANCE = Decimal("0.0000000001")
SEGMENT_TOLERANCE = Decimal("0.000000001")  # 1e-9 for spliced/observed-segment checks

MODEL_FLAG = "model_gld_tracking_lbma_pm_spot_minus_gld_expense"
ETF_FLAG = "observed_gld_etf_adjusted_total_return"
FFILL_FLAG = "observed_gld_us_open_lbma_holiday_close_gld_step"
OBSERVED_FLAGS = {ETF_FLAG, FFILL_FLAG}
GLD_EXPENSE_RATIO = Decimal("0.0040")


def read_csv(path: Path) -> list[dict[str, str]]:
    if not path.exists():
        pytest.skip(f"{path} does not exist yet")
    with path.open(newline="", encoding="utf-8") as handle:
        return list(csv.DictReader(handle))


def decimal_value(value: str) -> Decimal:
    return Decimal(value)


def gld_adjclose_by_date() -> dict[str, Decimal]:
    raw = json.loads(RAW_GLD.read_text(encoding="utf-8"))
    result = raw["chart"]["result"][0]
    timestamps = result.get("timestamp") or []
    adjclose = result.get("indicators", {}).get("adjclose", [{}])[0].get("adjclose", [])
    out: dict[str, Decimal] = {}
    for index, ts in enumerate(timestamps):
        value = adjclose[index] if index < len(adjclose) else None
        if value is None:
            continue
        day = datetime.fromtimestamp(ts, timezone.utc).date().isoformat()
        out[day] = Decimal(str(value))
    return out


def test_gold_scaffold_paths_exist():
    assert MANIFEST.exists()
    assert Path("sources/citations/gold.md").exists()


def test_gold_processed_outputs_exist():
    assert DATASET.exists()
    assert DATASET.stat().st_size > 0
    assert PARQUET_DATASET.exists()
    assert PARQUET_DATASET.stat().st_size > 0


def test_gold_yahoo_compatible_schema():
    with DATASET.open(newline="", encoding="utf-8") as handle:
        reader = csv.reader(handle)
        header = next(reader)

    assert header[: len(YAHOO_COLUMNS)] == YAHOO_COLUMNS
    for column in PROJECT_COLUMNS:
        assert column in header


def test_gold_minimum_coverage_and_unique_sorted_dates():
    rows = read_csv(DATASET)
    dates = [date.fromisoformat(row["Date"]) for row in rows]

    first_date = min(dates)
    assert first_date >= MIN_START_DATE
    assert first_date <= MIN_START_DATE + timedelta(days=MAX_START_LAG_DAYS)
    assert len(dates) == len(set(dates))
    assert dates == sorted(dates)


def test_gold_levels_positive_and_adj_close_carries_fee_drag():
    """Close is pure spot; Adj Close tracks GLD (with fee), so it ends below Close."""
    rows = read_csv(DATASET)

    for row in rows:
        assert decimal_value(row["Close"]) > 0
        assert decimal_value(row["Adj Close"]) > 0

    first, last = rows[0], rows[-1]
    # Anchored equal on day one, then the GLD expense drag pulls Adj Close below Close.
    assert decimal_value(first["Adj Close"]) == decimal_value(first["Close"])
    assert decimal_value(last["Adj Close"]) < decimal_value(last["Close"])


def test_gold_price_return_recomputes_from_close():
    """Price Return is the pure spot return derived from Close."""
    rows = read_csv(DATASET)
    previous_close: Decimal | None = None
    for row in rows:
        close = decimal_value(row["Close"])
        if previous_close is None:
            assert row["Price Return"] == ""
        else:
            expected = close / previous_close - Decimal("1")
            assert abs(decimal_value(row["Price Return"]) - expected) <= RETURN_TOLERANCE
        previous_close = close


def test_gold_total_return_recomputes_from_adj_close():
    rows = read_csv(DATASET)
    previous_adj: Decimal | None = None
    for row in rows:
        adj = decimal_value(row["Adj Close"])
        if previous_adj is None:
            assert row["Total Return"] == ""
        else:
            expected = adj / previous_adj - Decimal("1")
            assert abs(decimal_value(row["Total Return"]) - expected) <= SEGMENT_TOLERANCE
        previous_adj = adj


def test_gold_close_matches_raw_lbma_pm_source():
    rows = read_csv(DATASET)
    if not RAW_LBMA_PM.exists():
        pytest.skip(f"{RAW_LBMA_PM} does not exist yet")

    raw = json.loads(RAW_LBMA_PM.read_text(encoding="utf-8"))
    raw_by_date = {
        item["d"]: Decimal(str(item["v"][0]))
        for item in raw
        if item.get("v") and item["v"][0] is not None and date.fromisoformat(item["d"]) >= MIN_START_DATE
    }

    checked = 0
    for row in rows:
        if row["Quality Flag"] == FFILL_FLAG:
            # NYSE-open / LBMA-closed day: no LBMA fix that date; Close is GLD-stepped, not an LBMA value.
            assert row["Date"] not in raw_by_date
            assert decimal_value(row["Close"]) > 0
        else:
            assert row["Date"] in raw_by_date
            assert decimal_value(row["Close"]) == raw_by_date[row["Date"]]
            checked += 1

    assert checked > 10000


def test_gold_model_segment_applies_gld_expense_drag():
    """Modeled rows: Total Return == spot price return minus GLD expense accrual (actual/365)."""
    rows = read_csv(DATASET)
    prev_close: Decimal | None = None
    prev_date: date | None = None
    checked = 0
    for row in rows:
        close = decimal_value(row["Close"])
        cur_date = date.fromisoformat(row["Date"])
        if prev_close is not None and row["Quality Flag"] == MODEL_FLAG:
            days = Decimal((cur_date - prev_date).days)
            fee_factor = Decimal("1") - GLD_EXPENSE_RATIO * days / Decimal("365")
            expected = (close / prev_close) * fee_factor - Decimal("1")
            assert abs(decimal_value(row["Total Return"]) - expected) <= SEGMENT_TOLERANCE
            checked += 1
        prev_close = close
        prev_date = cur_date
    assert checked > 8000  # 1970 -> 2004 modeled segment


def test_gold_observed_segment_tracks_gld_exactly():
    """In the observed era Adj Close is exactly proportional to GLD's adjusted close.

    The observed era runs on GLD's (NYSE) trading calendar so the dataset aligns with GLD
    day-for-day; this is what lets a return-based backtest reproduce GLD without calendar drift.
    """
    rows = read_csv(DATASET)
    if not RAW_GLD.exists():
        pytest.skip(f"{RAW_GLD} does not exist yet")
    gld = gld_adjclose_by_date()

    ratios: list[Decimal] = []
    observed_dates: list[str] = []
    ffill_rows = 0
    for row in rows:
        if row["Quality Flag"] in OBSERVED_FLAGS:
            assert row["Date"] in gld, f"observed row {row['Date']} has no GLD obs"
            ratios.append(decimal_value(row["Adj Close"]) / gld[row["Date"]])
            observed_dates.append(row["Date"])
            if row["Quality Flag"] == FFILL_FLAG:
                ffill_rows += 1

    assert len(ratios) > 4000  # GLD observed segment row count
    rmin, rmax = min(ratios), max(ratios)
    # Constant proportionality => GOLDPM Adj Close *is* GLD (rescaled) in the modern era.
    assert (rmax - rmin) / rmin <= SEGMENT_TOLERANCE

    # Observed dates must be exactly GLD's trading days (so the backtester's date intersection
    # keeps every GLD day -- no calendar-mismatch drift).
    gld_after = sorted(d for d in gld if d >= min(observed_dates))
    assert observed_dates == gld_after
    assert ffill_rows > 50  # NYSE-open / LBMA-closed UK bank holidays
