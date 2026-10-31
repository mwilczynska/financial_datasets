"""Contract checks shared by the six 2x daily-reset datasets."""

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

from leveraged_2x import (  # noqa: E402
    CONFIGS,
    UST_BORROW_SPREAD,
    UST_EXPENSE_RATIO,
    calibration_stats,
    close_series,
    load_base_total_returns,
    make_irx_lookup,
    overlap_returns,
    raw_paths,
    synthetic_return,
)

YAHOO_COLUMNS = ["Date", "Open", "High", "Low", "Close", "Adj Close", "Volume"]
PROJECT_COLUMNS = ["Price Return", "Total Return", "Source", "Quality Flag", "Source Notes"]
MIN_START_DATE = date(1970, 1, 1)
MAX_START_LAG_DAYS = 7
RETURN_TOLERANCE = Decimal("0.0000000001")
MODEL_TOLERANCE = Decimal("0.000000001")
ROOT = Path(".")
STEMS = sorted(CONFIGS)
FUND_STEMS = [stem for stem in STEMS if CONFIGS[stem].fund]
MODELED_STEMS = [stem for stem in STEMS if not CONFIGS[stem].fund]
# WLDU began trading on 2026-03-10; its overlap is too short to calibrate a spread.
CALIBRATED_STEMS = [stem for stem in FUND_STEMS if CONFIGS[stem].fund != "WLDU"]


def read_csv(path: Path) -> list[dict[str, str]]:
    if not path.exists():
        pytest.skip(f"{path} does not exist yet")
    with path.open(newline="", encoding="utf-8") as handle:
        return list(csv.DictReader(handle))


def load_raw(path: Path | None) -> dict:
    if path is None or not path.exists():
        pytest.skip(f"{path} does not exist")
    return json.loads(path.read_text(encoding="utf-8"))


def dataset(stem: str) -> Path:
    return Path(f"data/processed/{stem}.csv")


@pytest.mark.parametrize("stem", STEMS)
def test_scaffold_and_outputs_exist(stem):
    assert Path(f"sources/manifests/{stem}.yml").exists()
    assert Path(f"sources/citations/{stem}.md").exists()
    assert Path(f"docs/methodology_{CONFIGS[stem].alias.lower()}.md").exists()
    for suffix in (".csv", ".parquet"):
        path = Path(f"data/processed/{stem}{suffix}")
        assert path.exists() and path.stat().st_size > 0


@pytest.mark.parametrize("stem", STEMS)
def test_yahoo_schema_and_base_calendar(stem):
    with dataset(stem).open(newline="", encoding="utf-8") as handle:
        header = next(csv.reader(handle))
    assert header == YAHOO_COLUMNS + PROJECT_COLUMNS
    rows = read_csv(dataset(stem))
    base = read_csv(Path(f"data/processed/{CONFIGS[stem].base_asset_id}.csv"))
    dates = [row["Date"] for row in rows]
    assert dates == sorted(set(dates))
    first = date.fromisoformat(dates[0])
    assert MIN_START_DATE <= first <= MIN_START_DATE + timedelta(days=MAX_START_LAG_DAYS)
    # The 2x series inherits its base calendar exactly; it may trail by a refresh.
    assert dates == [row["Date"] for row in base][: len(dates)]


@pytest.mark.parametrize("stem", STEMS)
def test_levels_and_return_arithmetic(stem):
    previous: Decimal | None = None
    for row in read_csv(dataset(stem)):
        assert row["Close"] == row["Adj Close"]
        assert row["Price Return"] == row["Total Return"]
        level = Decimal(row["Adj Close"])
        assert level > 0
        if previous is None:
            assert level == Decimal("100") and row["Total Return"] == ""
        else:
            assert abs(Decimal(row["Total Return"]) - (level / previous - 1)) <= RETURN_TOLERANCE
        previous = level


@pytest.mark.parametrize("stem", STEMS)
def test_segment_flags(stem):
    config = CONFIGS[stem]
    flags = [row["Quality Flag"] for row in read_csv(dataset(stem))]
    assert flags[0] == config.synth_flag
    if not config.fund:
        assert set(flags) == {config.synth_flag}
        return
    assert set(flags) == {config.synth_flag, config.etf_flag}
    assert flags[-1] == config.etf_flag
    assert sum(a != b for a, b in zip(flags, flags[1:])) == 1


@pytest.mark.parametrize("stem", MODELED_STEMS)
def test_fundless_exposures_use_ust_parameters(stem):
    config = CONFIGS[stem]
    assert config.expense_ratio == UST_EXPENSE_RATIO == CONFIGS["intermediate_term_us_treasury_2x"].expense_ratio
    assert config.borrow_spread == UST_BORROW_SPREAD == CONFIGS["intermediate_term_us_treasury_2x"].borrow_spread
    assert "_ust_" not in config.synth_flag  # Never mistaken for an observed UST row.


@pytest.mark.parametrize("stem", FUND_STEMS)
def test_observed_segment_matches_raw_fund_returns(stem):
    config = CONFIGS[stem]
    adj = close_series(load_raw(raw_paths(config, ROOT)[1]), "adjclose")
    checked = 0
    previous_adj: float | None = None
    for row in read_csv(dataset(stem)):
        current = adj.get(row["Date"])
        if row["Quality Flag"] == config.etf_flag:
            if current is None:
                continue  # Rows newer than the local raw cache came from the daily updater.
            expected = Decimal(str(current)) / Decimal(str(previous_adj)) - 1
            assert abs(Decimal(row["Total Return"]) - expected) <= MODEL_TOLERANCE
            checked += 1
        if current is not None:
            previous_adj = current
    assert checked > 100


@pytest.mark.parametrize("stem", STEMS)
def test_synthetic_segment_matches_daily_reset_model(stem):
    config = CONFIGS[stem]
    get_irx = make_irx_lookup(load_raw(raw_paths(config, ROOT)[0]))
    base_tr = dict(load_base_total_returns(Path(f"data/processed/{config.base_asset_id}.csv")))
    irx_last = max(close_series(load_raw(raw_paths(config, ROOT)[0]), "close"))
    previous_date: date | None = None
    checked = 0
    for row in read_csv(dataset(stem)):
        current = date.fromisoformat(row["Date"])
        if row["Quality Flag"] == config.synth_flag and previous_date is not None and row["Date"] <= irx_last:
            expected = synthetic_return(config, base_tr[row["Date"]], get_irx(row["Date"]),
                                        Decimal((current - previous_date).days))
            assert abs(Decimal(row["Total Return"]) - expected) <= MODEL_TOLERANCE
            checked += 1
        previous_date = current
    assert checked > 9000


@pytest.mark.parametrize("stem", CALIBRATED_STEMS)
def test_model_tracks_fund_over_live_overlap(stem):
    config = CONFIGS[stem]
    irx_path, fund_path = raw_paths(config, ROOT)
    model, observed = overlap_returns(
        config, load_base_total_returns(Path(f"data/processed/{config.base_asset_id}.csv")),
        make_irx_lookup(load_raw(irx_path)), close_series(load_raw(fund_path), "adjclose"))
    stats = calibration_stats(model, observed)
    assert stats["overlap_days"] > 4000
    assert 0.98 <= stats["cumulative_ratio_model_over_etf"] <= 1.02
    assert stats["daily_return_correlation"] > 0.95
