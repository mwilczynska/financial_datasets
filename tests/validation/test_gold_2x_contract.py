import csv
import json
import statistics
import sys
from datetime import date, timedelta
from decimal import Decimal
from pathlib import Path

import pytest

SRC = Path(__file__).resolve().parents[2] / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from build_gold_2x import (  # noqa: E402
    SYNTH_FLAG,
    ETF_FLAG,
    HOLIDAY_FLAG,
    close_series,
    make_irx_lookup,
    _synthetic_return,
)

DATASET = Path("data/processed/gold_2x.csv")
PARQUET_DATASET = Path("data/processed/gold_2x.parquet")
BASE_DATASET = Path("data/processed/gold.csv")
IRX_RAW = Path("sources/raw/gold_2x_yahoo_irx_chart.json")
UGL_RAW = Path("sources/raw/gold_2x_yahoo_ugl_chart.json")
LBMA_RAW = Path("sources/raw/gold_lbma_gold_pm.json")
MANIFEST = Path("sources/manifests/gold_2x.yml")
CITATION = Path("sources/citations/gold_2x.md")

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


def _corr(model: list[float], observed: list[float]) -> float:
    n = len(model)
    mean_m, mean_o = sum(model) / n, sum(observed) / n
    cov = sum((m - mean_m) * (o - mean_o) for m, o in zip(model, observed))
    var_m = sum((m - mean_m) ** 2 for m in model)
    var_o = sum((o - mean_o) ** 2 for o in observed)
    return cov / (var_m**0.5 * var_o**0.5)


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
    holiday = [r for r in rows if r["Quality Flag"] == HOLIDAY_FLAG]
    assert len(synth) + len(observed) + len(holiday) == len(rows)
    assert len(synth) > 9000
    assert len(observed) > 3500
    flags = [r["Quality Flag"] for r in rows]
    assert flags[0] == SYNTH_FLAG
    # The final row is in the observed era (either a UGL trading day or a US-holiday flat row,
    # depending on the calendar of the most recent build date).
    assert flags[-1] in (ETF_FLAG, HOLIDAY_FLAG)

    # GOLD2X inherits GOLDPM's calendar: the observed era runs on the ETF's (NYSE) trading days,
    # so it aligns with UGL day-for-day. The synthetic model is NOT used after inception, and the
    # holiday-flat path (UGL not trading on a base trading day) is effectively never needed now that
    # the base is on the NYSE calendar -- but if present, such rows must be flat.
    inception = min(r["Date"] for r in observed)
    assert all(r["Quality Flag"] == SYNTH_FLAG for r in rows if r["Date"] < inception)
    assert not any(r["Date"] > inception for r in synth)  # no synthetic fills in the observed era
    assert all(r["Date"] > inception for r in holiday)
    assert all(dval(r["Total Return"]) == Decimal("0") for r in holiday)


# --- Observed UGL segment matches the raw source ---------------------------------


def test_observed_segment_matches_raw_ugl_adjusted_returns():
    rows = read_csv(DATASET)
    ugl_adj = close_series(load_raw(UGL_RAW), "adjclose")

    # Observed returns are computed against the most recent UGL close (which may be an earlier
    # date than the previous dataset row when a US-holiday synthetic row sits in between), exactly
    # as the build does.
    checked = 0
    last_ugl: float | None = None
    for row in rows:
        adj = ugl_adj.get(row["Date"])
        if row["Quality Flag"] == ETF_FLAG:
            assert adj is not None and last_ugl is not None
            expected = Decimal(str(adj)) / Decimal(str(last_ugl)) - Decimal("1")
            assert abs(dval(row["Total Return"]) - expected) <= MODEL_TOLERANCE
            checked += 1
        elif row["Quality Flag"] == HOLIDAY_FLAG:
            assert adj is None  # UGL genuinely did not trade
            assert dval(row["Total Return"]) == Decimal("0")
        if adj is not None:
            last_ugl = adj
    assert checked > 3500


def test_observed_dataset_tracks_ugl_cumulatively():
    """Regression guard: in the observed era the dataset NAV is exactly proportional to UGL.

    The previous build inserted synthetic fills on US-market holidays AND let UGL's reopen return
    span the same holiday, double-counting the holiday's gold move and inflating the NAV ~34% vs
    UGL over 2008-2026. Holding holidays flat instead makes Adj Close a constant multiple of UGL.
    """
    rows = read_csv(DATASET)
    ugl_adj = close_series(load_raw(UGL_RAW), "adjclose")

    ratios: list[Decimal] = []
    for row in rows:
        if row["Quality Flag"] == ETF_FLAG:
            adj = ugl_adj.get(row["Date"])
            assert adj is not None
            ratios.append(dval(row["Adj Close"]) / Decimal(str(adj)))

    assert len(ratios) > 3500
    rmin, rmax = min(ratios), max(ratios)
    assert (rmax - rmin) / rmin <= MODEL_TOLERANCE


# --- Synthetic segment matches the daily-reset model -----------------------------


def test_synthetic_segment_matches_daily_reset_model():
    rows = read_csv(DATASET)
    base_rows = read_csv(BASE_DATASET)
    # The 2x model builds on GOLDPM's pure-spot Price Return (not Total Return, which now carries
    # GLD's expense drag).
    base_tr = {r["Date"]: (Decimal(r["Price Return"]) if r["Price Return"] else None) for r in base_rows}
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
            assert abs(dval(row["Close"]) - level) <= Decimal("0.0001")
            checked += 1
        previous_date = current_date
    assert checked > 9000


# --- Live overlap calibration against UGL ----------------------------------------


def _lbma_spot_returns() -> list[tuple[str, Decimal]]:
    """Clean LBMA-calendar daily spot returns from the raw LBMA PM source."""
    raw = json.loads(LBMA_RAW.read_text(encoding="utf-8"))
    fixings = sorted(
        (item["d"], float(item["v"][0]))
        for item in raw
        if item.get("v") and item["v"][0] is not None and date.fromisoformat(item["d"]) >= MIN_START_DATE
    )
    out: list[tuple[str, Decimal]] = []
    prev: float | None = None
    for iso, close in fixings:
        if prev is not None:
            out.append((iso, Decimal(str(close / prev - 1.0))))
        prev = close
    return out


def test_model_tracks_ugl_over_live_overlap():
    """Validate the borrowing-spread calibration: recompute the 2x model over the UGL overlap and
    compare to actual UGL.

    This is computed on the **clean LBMA (London) calendar** spot returns straight from the raw
    LBMA source -- the basis the spread was calibrated against -- not on the shipped GOLDPM
    Price Return, whose observed era now runs on the NYSE calendar (the LBMA-vs-US-close timing
    basis interacting with that calendar inflates a daily-reset continuous model). The shipped
    GOLD2X uses observed UGL returns after inception and is checked exactly by
    test_observed_dataset_tracks_ugl_cumulatively.

    GOLDPM is the LBMA PM fix (~10:30am ET); UGL closes at 4pm ET. Returns measured ~5.5 hours
    apart decorrelate, so the daily UGL-vs-model correlation is only ~0.67. The robust checks are
    therefore cumulative growth (calibration target) and the daily volatility ratio.
    """
    if not LBMA_RAW.exists():
        pytest.skip(f"{LBMA_RAW} does not exist yet")
    spot_returns = _lbma_spot_returns()
    ugl_adj = close_series(load_raw(UGL_RAW), "adjclose")
    get_irx = make_irx_lookup(load_raw(IRX_RAW))
    inception = min(ugl_adj)

    model: list[float] = []
    observed: list[float] = []
    previous_date: date | None = None
    prev_adj: float | None = None
    for d, u in spot_returns:
        cur = date.fromisoformat(d)
        adj = ugl_adj.get(d)
        if d >= inception and previous_date is not None and adj is not None and prev_adj is not None:
            delta_days = Decimal((cur - previous_date).days)
            model.append(float(_synthetic_return(u, get_irx(d), delta_days)))
            observed.append(adj / prev_adj - 1.0)
        previous_date = cur
        if adj is not None:
            prev_adj = adj

    assert len(model) > 3500
    cum_m, cum_o = 1.0, 1.0
    for m, o in zip(model, observed):
        cum_m *= 1 + m
        cum_o *= 1 + o

    # Cumulative growth over the overlap matches within 10% (calibration target).
    assert 0.90 <= cum_m / cum_o <= 1.10
    # Daily volatility scale matches UGL within 20% (confirms the 2x daily-reset magnitude).
    vol_ratio = statistics.pstdev(model) / statistics.pstdev(observed)
    assert 0.80 <= vol_ratio <= 1.20
    # Returns remain meaningfully positively correlated despite the LBMA-vs-US-close timing basis.
    assert _corr(model, observed) > 0.5
