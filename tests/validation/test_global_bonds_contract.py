import csv
import json
import math
import statistics
import sys
from datetime import date, timedelta
from decimal import Decimal
from pathlib import Path

import pytest

SRC = Path(__file__).resolve().parents[2] / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from build_global_bonds import (  # noqa: E402
    BND_WEIGHT,
    BWX_WEIGHT,
    EARLY_FLAG,
    ETF_BLEND_FLAG,
    close_series,
    jst_annual_unhedged_returns,
    jst_basket,
    parse_jst_rows,
)


DATASET = Path("data/processed/global_bonds.csv")
PARQUET_DATASET = Path("data/processed/global_bonds.parquet")
BUILD_META = Path("sources/manifests/global_bonds_build.json")
RAW_JST = Path("sources/raw/global_bonds_jst_macrohistory_r6.xlsx")
RAW_BND = Path("sources/raw/global_bonds_yahoo_bnd_chart.json")
RAW_BWX = Path("sources/raw/global_bonds_yahoo_bwx_chart.json")
MANIFEST = Path("sources/manifests/global_bonds.yml")
CITATION = Path("sources/citations/global_bonds.md")

YAHOO_COLUMNS = ["Date", "Open", "High", "Low", "Close", "Adj Close", "Volume"]
PROJECT_COLUMNS = ["Price Return", "Total Return", "Source", "Quality Flag", "Source Notes"]
RETURN_TOLERANCE = Decimal("0.0000000001")
ANNUAL_TOLERANCE = Decimal("0.00000003")


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


def test_global_bonds_scaffold_paths_exist():
    assert MANIFEST.exists()
    assert CITATION.exists()


def test_global_bonds_processed_outputs_exist():
    assert DATASET.exists() and DATASET.stat().st_size > 0
    assert PARQUET_DATASET.exists() and PARQUET_DATASET.stat().st_size > 0


def test_global_bonds_yahoo_compatible_schema():
    with DATASET.open(newline="", encoding="utf-8") as handle:
        header = next(csv.reader(handle))
    assert header[: len(YAHOO_COLUMNS)] == YAHOO_COLUMNS
    for column in PROJECT_COLUMNS:
        assert column in header


def test_global_bonds_minimum_coverage_and_unique_sorted_dates():
    rows = read_csv(DATASET)
    dates = [date.fromisoformat(row["Date"]) for row in rows]
    assert dates[0] >= date(1970, 1, 1)
    assert dates[0] <= date(1970, 1, 1) + timedelta(days=7)
    assert dates == sorted(dates)
    assert len(dates) == len(set(dates))


def test_global_bonds_levels_positive_and_returns_recompute():
    rows = read_csv(DATASET)
    previous: Decimal | None = None
    for row in rows:
        close = dval(row["Close"])
        adjusted = dval(row["Adj Close"])
        assert close > 0
        assert adjusted > 0
        assert row["Close"] == row["Adj Close"]
        assert row["Price Return"] == row["Total Return"]
        if previous is None:
            assert row["Total Return"] == ""
        else:
            expected = adjusted / previous - Decimal("1")
            assert abs(dval(row["Total Return"]) - expected) <= RETURN_TOLERANCE
        previous = adjusted


def test_global_bonds_segment_flags_present_and_sized():
    rows = read_csv(DATASET)
    flags = [row["Quality Flag"] for row in rows]
    assert flags.count(EARLY_FLAG) > 9000
    assert flags.count(ETF_BLEND_FLAG) > 4500
    assert flags[0] == EARLY_FLAG
    assert flags[-1] == ETF_BLEND_FLAG


def test_global_bonds_early_segment_anchors_to_jst_annual_returns():
    # The de-smoothed early segment supplies the within-year path, but the per-year
    # overlay must still make each calendar year compound exactly to the JST basket.
    rows = [row for row in read_csv(DATASET) if row["Quality Flag"] == EARLY_FLAG]
    by_year: dict[int, list[dict[str, str]]] = {}
    for row in rows:
        by_year.setdefault(date.fromisoformat(row["Date"]).year, []).append(row)
    annual = jst_annual_unhedged_returns(parse_jst_rows(RAW_JST.read_bytes()))

    for year in range(1970, 2007):
        growth = Decimal("1")
        for row in by_year[year]:
            if row["Total Return"]:
                growth *= Decimal("1") + dval(row["Total Return"])
        observed = growth - Decimal("1")
        assert abs(observed - annual[year]) <= ANNUAL_TOLERANCE


def test_global_bonds_etf_segment_matches_bnd_bwx_blend():
    rows = read_csv(DATASET)
    bnd = close_series(load_raw(RAW_BND), "adjclose")
    bwx = close_series(load_raw(RAW_BWX), "adjclose")
    blend_returns: dict[str, Decimal] = {}
    prev_bnd: float | None = None
    prev_bwx: float | None = None
    for day in sorted(set(bnd) | set(bwx)):
        bnd_adj = bnd.get(day)
        bwx_adj = bwx.get(day)
        if bnd_adj is not None and bwx_adj is not None and prev_bnd is not None and prev_bwx is not None:
            bnd_ret = Decimal(str(bnd_adj)) / Decimal(str(prev_bnd)) - Decimal("1")
            bwx_ret = Decimal(str(bwx_adj)) / Decimal(str(prev_bwx)) - Decimal("1")
            blend_returns[day] = BND_WEIGHT * bnd_ret + BWX_WEIGHT * bwx_ret
        if bnd_adj is not None:
            prev_bnd = bnd_adj
        if bwx_adj is not None:
            prev_bwx = bwx_adj

    checked = 0
    for row in rows:
        if row["Quality Flag"] == ETF_BLEND_FLAG:
            expected = blend_returns[row["Date"]]
            assert abs(dval(row["Total Return"]) - expected) <= RETURN_TOLERANCE
            checked += 1
    assert checked > 4500


def _early_rows_by_year() -> dict[int, list[dict[str, str]]]:
    by_year: dict[int, list[dict[str, str]]] = {}
    for row in read_csv(DATASET):
        if row["Quality Flag"] == EARLY_FLAG:
            by_year.setdefault(date.fromisoformat(row["Date"]).year, []).append(row)
    return by_year


def test_global_bonds_early_segment_is_not_annual_smoothed():
    # Regression against the previous build, where every day in a year carried the
    # identical constant log return (exactly one distinct value per year). The de-smoothed
    # path must vary day to day, driven by genuine daily FX moves.
    by_year = _early_rows_by_year()
    for year in range(1971, 2007):
        distinct = {row["Total Return"] for row in by_year[year] if row["Total Return"]}
        assert len(distinct) > 100, f"{year} has only {len(distinct)} distinct daily returns"


def test_global_bonds_early_segment_has_realistic_volatility():
    # An unhedged global government-bond series in USD runs roughly 5-10% annualized vol.
    # A flat annual ramp would be ~0%; an inverted/garbled FX leg would blow well past 20%.
    returns = [
        float(row["Total Return"])
        for row in read_csv(DATASET)
        if row["Quality Flag"] == EARLY_FLAG and row["Total Return"]
    ]
    annualized_vol = statistics.pstdev(returns) * math.sqrt(252)
    assert 0.03 < annualized_vol < 0.20, f"early-segment annualized vol {annualized_vol:.3f} out of range"


def test_global_bonds_early_segment_fx_event_directions():
    # Sanity check on FX orientation and date alignment using two unambiguous USD shocks.
    # Plaza Accord (announced Sun 1985-09-22): the dollar fell hard, so an unhedged foreign
    # bond basket should jump on the next trading day. The 1978-11-01 Carter dollar-rescue
    # rally is the opposite: a sharp dollar gain should hit the basket. Getting FX inverted
    # would flip both signs.
    returns = {
        row["Date"]: float(row["Total Return"])
        for row in read_csv(DATASET)
        if row["Quality Flag"] == EARLY_FLAG and row["Total Return"]
    }
    assert returns["1985-09-23"] > 0.01
    assert returns["1978-11-02"] < -0.01


def test_global_bonds_basket_weights_are_economically_sane():
    # Guards the GDP-weighting fix. JST's nominal `gdp` column has inconsistent units across
    # countries (US in billions, Spain in millions of pesetas), so weighting by gdp/xrusd
    # mis-weights the basket toward small economies (US ~0.3%, ESP ~22%). Comparable real GDP
    # (rgdpmad x pop) must keep the U.S. the largest weight and the four largest economies a
    # clear majority of the basket.
    _, weights = jst_basket(parse_jst_rows(RAW_JST.read_bytes()))
    for year in (1975, 1985, 1995, 2005):
        w = weights[year]
        largest = max(w, key=lambda iso: w[iso])
        assert largest == "USA", f"{year}: largest weight is {largest}, expected USA"
        g4 = sum(w.get(iso, Decimal("0")) for iso in ("USA", "JPN", "GBR", "DEU"))
        assert g4 > Decimal("0.5"), f"{year}: G4 weight share {g4} too low"


def test_global_bonds_daily_rate_leg_coverage():
    # The three largest weights get a genuinely daily bond return (US in-repo Treasury TR from
    # 1970, Japan MoF 10y from 1986-07, UK BoE 10y spot from 1979); everyone else stays
    # monthly. This guards that the daily rate sources are actually wired into the build.
    if not BUILD_META.exists():
        pytest.skip("build metadata not present")
    coverage = json.loads(BUILD_META.read_text(encoding="utf-8"))["daily_rate_coverage"]
    assert coverage["USA"]["first"] <= "1970-01-31" and coverage["USA"]["count"] > 9000
    assert "1986-01-01" <= coverage["JPN"]["first"] <= "1986-12-31" and coverage["JPN"]["count"] > 4000
    assert "1979-01-01" <= coverage["GBR"]["first"] <= "1979-12-31" and coverage["GBR"]["count"] > 6000
