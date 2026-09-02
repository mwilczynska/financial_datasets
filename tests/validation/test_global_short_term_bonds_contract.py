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

from build_global_short_term_bonds import (  # noqa: E402
    EARLY_FLAG,
    ETF_BLEND_FLAG,
    REPRESENTATIVE_FEE_ANNUAL,
    close_series,
    jst_basket,
    parse_jst_rows,
    us_weight_by_year,
)


DATASET = Path("data/processed/global_short_term_bonds.csv")
PARQUET_DATASET = Path("data/processed/global_short_term_bonds.parquet")
BUILD_META = Path("sources/manifests/global_short_term_bonds_build.json")
RAW_JST = Path("sources/raw/global_short_term_bonds_jst_macrohistory_r6.xlsx")
RAW_SHY = Path("sources/raw/global_short_term_bonds_yahoo_shy_chart.json")
RAW_ISHG = Path("sources/raw/global_short_term_bonds_yahoo_ishg_chart.json")
RAW_BWZ = Path("sources/raw/global_short_term_bonds_yahoo_bwz_chart.json")
MANIFEST = Path("sources/manifests/global_short_term_bonds.yml")
CITATION = Path("sources/citations/global_short_term_bonds.md")

YAHOO_COLUMNS = ["Date", "Open", "High", "Low", "Close", "Adj Close", "Volume"]
PROJECT_COLUMNS = ["Price Return", "Total Return", "Source", "Quality Flag", "Source Notes"]
RETURN_TOLERANCE = Decimal("0.0000000001")


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


def test_glstbond_scaffold_paths_exist():
    assert MANIFEST.exists()
    assert CITATION.exists()


def test_glstbond_processed_outputs_exist():
    assert DATASET.exists() and DATASET.stat().st_size > 0
    assert PARQUET_DATASET.exists() and PARQUET_DATASET.stat().st_size > 0


def test_glstbond_yahoo_compatible_schema():
    with DATASET.open(newline="", encoding="utf-8") as handle:
        header = next(csv.reader(handle))
    assert header[: len(YAHOO_COLUMNS)] == YAHOO_COLUMNS
    for column in PROJECT_COLUMNS:
        assert column in header


def test_glstbond_minimum_coverage_and_unique_sorted_dates():
    rows = read_csv(DATASET)
    dates = [date.fromisoformat(row["Date"]) for row in rows]
    assert dates[0] >= date(1970, 1, 1)
    assert dates[0] <= date(1970, 1, 1) + timedelta(days=7)
    assert dates == sorted(dates)
    assert len(dates) == len(set(dates))


def test_glstbond_levels_positive_and_returns_recompute():
    # Close / Price Return are the GROSS-of-fee total return; Adj Close / Total Return are
    # NET of the modeled fee. Each level must recompute from its own return column.
    rows = read_csv(DATASET)
    prev_close: Decimal | None = None
    prev_adj: Decimal | None = None
    for row in rows:
        close = dval(row["Close"])
        adjusted = dval(row["Adj Close"])
        assert close > 0
        assert adjusted > 0
        if prev_close is None:
            assert row["Price Return"] == ""
            assert row["Total Return"] == ""
        else:
            assert abs(close / prev_close - Decimal("1") - dval(row["Price Return"])) <= RETURN_TOLERANCE
            assert abs(adjusted / prev_adj - Decimal("1") - dval(row["Total Return"])) <= RETURN_TOLERANCE
        prev_close = close
        prev_adj = adjusted


def test_glstbond_segment_flags_present_and_sized():
    rows = read_csv(DATASET)
    flags = [row["Quality Flag"] for row in rows]
    assert flags.count(EARLY_FLAG) > 9000
    assert flags.count(ETF_BLEND_FLAG) > 4000
    assert flags[0] == EARLY_FLAG
    assert flags[-1] == ETF_BLEND_FLAG


def test_glstbond_net_of_fee_drag_is_close_to_modeled_rate():
    # Adj Close (net) should fall below Close (gross) at very nearly the representative fee
    # rate over the model era. Checked at the model-era end, which spans 1970-01 to 2009-01.
    rows = [row for row in read_csv(DATASET) if row["Quality Flag"] == EARLY_FLAG]
    first, last = rows[0], rows[-1]
    years = (date.fromisoformat(last["Date"]) - date.fromisoformat(first["Date"])).days / 365.25
    gross = dval(last["Close"]) / dval(first["Close"])
    net = dval(last["Adj Close"]) / dval(first["Adj Close"])
    implied_fee = float(gross / net) ** (1.0 / years) - 1.0
    assert abs(implied_fee - float(REPRESENTATIVE_FEE_ANNUAL)) < 0.0003
    # Net must be strictly below gross throughout (fee always drags).
    for row in read_csv(DATASET):
        assert dval(row["Adj Close"]) <= dval(row["Close"]) + Decimal("1e-9")


def test_glstbond_observed_segment_matches_gdp_weighted_blend():
    # The observed era must reproduce the GDP-weighted, annually-rebalanced net blend:
    # w_us(year) * SHY + (1 - w_us(year)) * mean(ISHG, BWZ), from adjusted-close returns.
    rows = read_csv(DATASET)
    shy = close_series(load_raw(RAW_SHY), "adjclose")
    ishg = close_series(load_raw(RAW_ISHG), "adjclose")
    bwz = close_series(load_raw(RAW_BWZ), "adjclose")
    us_weight = us_weight_by_year(parse_jst_rows(RAW_JST.read_bytes()), 2100)

    def ret(series, prev, day):
        v = series.get(day)
        if v is None or prev is None:
            return None
        return Decimal(str(v)) / Decimal(str(prev)) - Decimal("1")

    blend: dict[str, Decimal] = {}
    prev_shy = prev_ishg = prev_bwz = None
    for day in sorted(set(shy) | set(ishg) | set(bwz)):
        r_shy = ret(shy, prev_shy, day)
        legs = [r for r in (ret(ishg, prev_ishg, day), ret(bwz, prev_bwz, day)) if r is not None]
        if r_shy is not None and legs:
            intl = sum(legs) / Decimal(len(legs))
            w = us_weight[int(day[:4])]
            blend[day] = w * r_shy + (Decimal("1") - w) * intl
        if day in shy:
            prev_shy = shy[day]
        if day in ishg:
            prev_ishg = ishg[day]
        if day in bwz:
            prev_bwz = bwz[day]

    checked = 0
    for row in rows:
        if row["Quality Flag"] == ETF_BLEND_FLAG:
            assert abs(dval(row["Total Return"]) - blend[row["Date"]]) <= RETURN_TOLERANCE
            checked += 1
    assert checked > 4000


def test_glstbond_early_segment_is_genuinely_daily():
    # Direct construction must produce a real daily path, not one constant return per year.
    by_year: dict[int, set[str]] = {}
    for row in read_csv(DATASET):
        if row["Quality Flag"] == EARLY_FLAG and row["Total Return"]:
            by_year.setdefault(date.fromisoformat(row["Date"]).year, set()).add(row["Total Return"])
    for year in range(1971, 2008):
        assert len(by_year[year]) > 100, f"{year} has only {len(by_year[year])} distinct daily returns"


def test_glstbond_early_segment_has_realistic_volatility():
    # Unhedged global SHORT-term government bonds in USD: FX dominates, rate duration is ~2yr,
    # so annualized vol sits roughly 3-12% (below the broad 10yr GLBOND, above a hedged book).
    returns = [
        float(row["Total Return"])
        for row in read_csv(DATASET)
        if row["Quality Flag"] == EARLY_FLAG and row["Total Return"]
    ]
    annualized_vol = statistics.pstdev(returns) * math.sqrt(252)
    assert 0.03 < annualized_vol < 0.12, f"early-segment annualized vol {annualized_vol:.3f} out of range"


def test_glstbond_early_segment_fx_event_directions():
    # FX orientation / date-alignment guard using two unambiguous USD shocks (shared with the
    # GLBOND build): Plaza Accord (1985-09-23, dollar fell -> basket up) and the Carter
    # dollar-rescue rally (1978-11-02, dollar up -> basket down).
    returns = {
        row["Date"]: float(row["Total Return"])
        for row in read_csv(DATASET)
        if row["Quality Flag"] == EARLY_FLAG and row["Total Return"]
    }
    assert returns["1985-09-23"] > 0.005
    assert returns["1978-11-02"] < -0.005


def test_glstbond_basket_weights_are_economically_sane():
    _, weights = jst_basket(parse_jst_rows(RAW_JST.read_bytes()))
    for year in (1975, 1985, 1995, 2005):
        w = weights[year]
        assert max(w, key=lambda iso: w[iso]) == "USA"
        g4 = sum(w.get(iso, Decimal("0")) for iso in ("USA", "JPN", "GBR", "DEU"))
        assert g4 > Decimal("0.5"), f"{year}: G4 weight share {g4} too low"


def test_glstbond_daily_rate_leg_coverage():
    # Short-end daily rate legs: US in-repo 2yr Treasury TR from 1970, Japan MoF 2yr JGB from
    # 1974-09 (twelve years earlier than the 10yr), UK BoE 2yr spot from 1979.
    if not BUILD_META.exists():
        pytest.skip("build metadata not present")
    coverage = json.loads(BUILD_META.read_text(encoding="utf-8"))["daily_rate_coverage"]
    assert coverage["USA"]["first"] <= "1970-01-31" and coverage["USA"]["count"] > 9000
    assert "1974-09-01" <= coverage["JPN"]["first"] <= "1974-12-31" and coverage["JPN"]["count"] > 7000
    assert "1979-01-01" <= coverage["GBR"]["first"] <= "1979-12-31" and coverage["GBR"]["count"] > 6000
