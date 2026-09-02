import csv
import json
import sys
from datetime import date, timedelta
from decimal import Decimal
from pathlib import Path

import pytest

SRC = Path(__file__).resolve().parents[2] / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from build_long_term_treasury_3x import (  # noqa: E402
    SYNTH_FLAG,
    ETF_FLAG,
    close_series,
    make_irx_lookup,
    _synthetic_return,
)

DATASET = Path("data/processed/long_term_us_treasury_3x.csv")
PARQUET_DATASET = Path("data/processed/long_term_us_treasury_3x.parquet")
BASE_DATASET = Path("data/processed/long_term_us_treasury.csv")
IRX_RAW = Path("sources/raw/long_term_us_treasury_3x_yahoo_irx_chart.json")
TMF_RAW = Path("sources/raw/long_term_us_treasury_3x_yahoo_tmf_chart.json")
MANIFEST = Path("sources/manifests/long_term_us_treasury_3x.yml")
CITATION = Path("sources/citations/long_term_us_treasury_3x.md")

YAHOO_COLUMNS = ["Date", "Open", "High", "Low", "Close", "Adj Close", "Volume"]
PROJECT_COLUMNS = ["Price Return", "Total Return", "Source", "Quality Flag", "Source Notes"]
MIN_START_DATE = date(1970, 1, 1)
MAX_START_LAG_DAYS = 7
RETURN_TOLERANCE = Decimal("0.0000000001")
MODEL_TOLERANCE = Decimal("0.000000001")


def read_csv(path: Path) -> list[dict[str, str]]:
    if not path.exists():
        pytest.skip(f"{path} does not exist yet")
    with path.open(newline="", encoding="utf-8") as handle:
        return list(csv.DictReader(handle))


def dval(value: str) -> Decimal:
    return Decimal(value)


def load_raw(path: Path) -> dict:
    if not path.exists():
        pytest.skip(f"{path} does not exist")
    return json.loads(path.read_text(encoding="utf-8"))


# --- Scaffolding -----------------------------------------------------------------


def test_validation_scaffold_paths_exist():
    assert Path("docs/source_registry.md").exists()
    assert Path("docs/validation.md").exists()
    assert MANIFEST.exists()
    assert CITATION.exists()


def test_processed_outputs_exist():
    assert DATASET.exists() and DATASET.stat().st_size > 0
    assert PARQUET_DATASET.exists() and PARQUET_DATASET.stat().st_size > 0


# --- Schema and coverage ---------------------------------------------------------


def test_yahoo_compatible_schema():
    with DATASET.open(newline="", encoding="utf-8") as handle:
        header = next(csv.reader(handle))
    assert header[: len(YAHOO_COLUMNS)] == YAHOO_COLUMNS
    for column in PROJECT_COLUMNS:
        assert column in header


def test_minimum_coverage_and_unique_sorted_dates():
    rows = read_csv(DATASET)
    dates = [date.fromisoformat(row["Date"]) for row in rows]
    first_date = min(dates)
    assert first_date >= MIN_START_DATE
    assert first_date <= MIN_START_DATE + timedelta(days=MAX_START_LAG_DAYS)
    assert len(dates) == len(set(dates))
    assert dates == sorted(dates)


def test_positive_levels_throughout():
    rows = read_csv(DATASET)
    for row in rows:
        assert dval(row["Close"]) > 0
        assert dval(row["Adj Close"]) > 0


def test_close_equals_adj_close_and_price_equals_total_return():
    rows = read_csv(DATASET)
    for row in rows:
        assert row["Close"] == row["Adj Close"]
        assert row["Price Return"] == row["Total Return"]


def test_total_return_recomputes_from_adjusted_close():
    rows = read_csv(DATASET)
    previous: Decimal | None = None
    for row in rows:
        adjusted = dval(row["Adj Close"])
        if previous is None:
            assert row["Total Return"] == ""
        else:
            expected = adjusted / previous - Decimal("1")
            assert abs(dval(row["Total Return"]) - expected) <= RETURN_TOLERANCE
        previous = adjusted


# --- Segment composition ---------------------------------------------------------


def test_segment_flags_present_and_sized():
    rows = read_csv(DATASET)
    synth = [r for r in rows if r["Quality Flag"] == SYNTH_FLAG]
    observed = [r for r in rows if r["Quality Flag"] == ETF_FLAG]
    assert len(synth) + len(observed) == len(rows)
    assert len(synth) > 9000
    assert len(observed) > 3500
    flags = [r["Quality Flag"] for r in rows]
    assert flags[0] == SYNTH_FLAG
    assert flags[-1] == ETF_FLAG
    transitions = sum(1 for a, b in zip(flags, flags[1:]) if a != b)
    assert transitions == 1


# --- Observed TMF segment matches the raw source ---------------------------------


def test_observed_segment_matches_raw_tmf_adjusted_returns():
    rows = read_csv(DATASET)
    tmf_adj = close_series(load_raw(TMF_RAW), "adjclose")

    checked = 0
    previous_date: str | None = None
    for row in rows:
        if row["Quality Flag"] == ETF_FLAG and previous_date is not None:
            cur = tmf_adj.get(row["Date"])
            prev = tmf_adj.get(previous_date)
            assert cur is not None and prev is not None
            expected = Decimal(str(cur)) / Decimal(str(prev)) - Decimal("1")
            assert abs(dval(row["Total Return"]) - expected) <= MODEL_TOLERANCE
            checked += 1
        previous_date = row["Date"]
    assert checked > 3500


# --- Synthetic segment matches the daily-reset model -----------------------------


def test_synthetic_segment_matches_daily_reset_model():
    rows = read_csv(DATASET)
    base_rows = read_csv(BASE_DATASET)
    base_tr = {r["Date"]: (Decimal(r["Total Return"]) if r["Total Return"] else None) for r in base_rows}
    get_irx = make_irx_lookup(load_raw(IRX_RAW))

    level = Decimal("100")
    previous_date: date | None = None
    checked = 0
    for row in rows:
        if row["Quality Flag"] != SYNTH_FLAG:
            break
        current_date = date.fromisoformat(row["Date"])
        if previous_date is None:
            assert dval(row["Close"]) == Decimal("100")
        else:
            delta_days = Decimal((current_date - previous_date).days)
            lev_ret = _synthetic_return(base_tr.get(row["Date"]), get_irx(row["Date"]), delta_days)
            level *= Decimal("1") + lev_ret
            assert abs(dval(row["Total Return"]) - lev_ret) <= MODEL_TOLERANCE
            assert abs(dval(row["Close"]) - level) <= Decimal("0.00001")
            checked += 1
        previous_date = current_date
    assert checked > 9000


# --- Live overlap calibration against TMF ----------------------------------------


def test_model_tracks_tmf_over_live_overlap():
    """Recompute the model over the TMF live period and compare to actual TMF."""
    base_rows = read_csv(BASE_DATASET)
    base_tr = {r["Date"]: (Decimal(r["Total Return"]) if r["Total Return"] else None) for r in base_rows}
    base_dates = [r["Date"] for r in base_rows]
    tmf_adj = close_series(load_raw(TMF_RAW), "adjclose")
    get_irx = make_irx_lookup(load_raw(IRX_RAW))
    inception = min(tmf_adj)

    model: list[float] = []
    observed: list[float] = []
    previous_date: date | None = None
    prev_adj: float | None = None
    for d in base_dates:
        cur = date.fromisoformat(d)
        adj = tmf_adj.get(d)
        if d >= inception and previous_date is not None and adj is not None and prev_adj is not None:
            delta_days = Decimal((cur - previous_date).days)
            model_ret = float(_synthetic_return(base_tr.get(d), get_irx(d), delta_days))
            model.append(model_ret)
            observed.append(adj / prev_adj - 1.0)
        previous_date = cur
        if adj is not None:
            prev_adj = adj

    assert len(model) > 3500
    n = len(model)
    mean_m, mean_o = sum(model) / n, sum(observed) / n
    cov = sum((m - mean_m) * (o - mean_o) for m, o in zip(model, observed))
    var_m = sum((m - mean_m) ** 2 for m in model)
    var_o = sum((o - mean_o) ** 2 for o in observed)
    corr = cov / (var_m**0.5 * var_o**0.5)
    cum_m, cum_o = 1.0, 1.0
    for m, o in zip(model, observed):
        cum_m *= 1 + m
        cum_o *= 1 + o

    # Daily returns are very highly correlated with actual TMF.
    assert corr > 0.99
    # Cumulative growth over the overlap matches within 10% (calibration target).
    assert 0.90 <= cum_m / cum_o <= 1.10
