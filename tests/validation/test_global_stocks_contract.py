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

from build_global_stocks import (  # noqa: E402
    FF_DEVELOPED_FLAG,
    MSCI_ANNUAL_SCALED_FLAG,
    MSCI_WORLD_GROSS_ANNUAL_RETURNS,
    VT_FLAG,
    close_series,
    load_ff_developed_returns,
)


DATASET = Path("data/processed/global_stocks.csv")
PARQUET_DATASET = Path("data/processed/global_stocks.parquet")
RAW_FF = Path("sources/raw/Developed_3_Factors_Daily_CSV.zip")
RAW_VT = Path("sources/raw/global_stocks_yahoo_vt_chart.json")
MANIFEST = Path("sources/manifests/global_stocks.yml")
CITATION = Path("sources/citations/global_stocks.md")

YAHOO_COLUMNS = ["Date", "Open", "High", "Low", "Close", "Adj Close", "Volume"]
PROJECT_COLUMNS = ["Price Return", "Total Return", "Source", "Quality Flag", "Source Notes"]
RETURN_TOLERANCE = Decimal("0.0000000001")
ANNUAL_TOLERANCE = Decimal("0.00000002")


def read_csv(path: Path) -> list[dict[str, str]]:
    if not path.exists():
        pytest.skip(f"{path} does not exist yet")
    with path.open(newline="", encoding="utf-8") as handle:
        return list(csv.DictReader(handle))


def dval(value: str) -> Decimal:
    return Decimal(value)


def test_global_stocks_scaffold_paths_exist():
    assert MANIFEST.exists()
    assert CITATION.exists()


def test_global_stocks_processed_outputs_exist():
    assert DATASET.exists() and DATASET.stat().st_size > 0
    assert PARQUET_DATASET.exists() and PARQUET_DATASET.stat().st_size > 0


def test_global_stocks_yahoo_compatible_schema():
    with DATASET.open(newline="", encoding="utf-8") as handle:
        header = next(csv.reader(handle))
    assert header[: len(YAHOO_COLUMNS)] == YAHOO_COLUMNS
    for column in PROJECT_COLUMNS:
        assert column in header


def test_global_stocks_minimum_coverage_and_unique_sorted_dates():
    rows = read_csv(DATASET)
    dates = [date.fromisoformat(row["Date"]) for row in rows]
    first_date = dates[0]
    assert first_date >= date(1970, 1, 1)
    assert first_date <= date(1970, 1, 1) + timedelta(days=7)
    assert dates == sorted(dates)
    assert len(dates) == len(set(dates))


def test_global_stocks_levels_positive_and_returns_recompute():
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


def test_global_stocks_segment_flags_present_and_sized():
    rows = read_csv(DATASET)
    flags = [row["Quality Flag"] for row in rows]
    assert flags.count(MSCI_ANNUAL_SCALED_FLAG) > 5000
    assert flags.count(FF_DEVELOPED_FLAG) > 4500
    assert flags.count(VT_FLAG) > 4000
    assert flags[-1] == VT_FLAG


def test_global_stocks_early_model_matches_msci_annual_returns():
    rows = [row for row in read_csv(DATASET) if row["Quality Flag"] == MSCI_ANNUAL_SCALED_FLAG]
    by_year: dict[int, list[dict[str, str]]] = {}
    for row in rows:
        by_year.setdefault(date.fromisoformat(row["Date"]).year, []).append(row)
    for year, target in MSCI_WORLD_GROSS_ANNUAL_RETURNS.items():
        year_rows = by_year[year]
        growth = Decimal("1")
        for row in year_rows:
            if row["Total Return"]:
                growth *= Decimal("1") + dval(row["Total Return"])
        observed = growth - Decimal("1")
        assert abs(observed - target) <= ANNUAL_TOLERANCE


def test_global_stocks_ff_segment_matches_raw_fama_french_developed_returns():
    rows = read_csv(DATASET)
    ff_returns = load_ff_developed_returns(RAW_FF)
    checked = 0
    for row in rows:
        if row["Quality Flag"] != FF_DEVELOPED_FLAG:
            continue
        expected = ff_returns[row["Date"]]
        assert abs(dval(row["Total Return"]) - expected) <= RETURN_TOLERANCE
        checked += 1
    assert checked > 4500


def test_global_stocks_vt_segment_matches_raw_vt_adjusted_returns():
    rows = read_csv(DATASET)
    vt_adj = close_series(json.loads(RAW_VT.read_text(encoding="utf-8")), "adjclose")
    checked = 0
    previous_adj: float | None = None
    for row in rows:
        adj = vt_adj.get(row["Date"])
        if row["Quality Flag"] == VT_FLAG:
            assert adj is not None and previous_adj is not None
            expected = Decimal(str(adj)) / Decimal(str(previous_adj)) - Decimal("1")
            assert abs(dval(row["Total Return"]) - expected) <= RETURN_TOLERANCE
            checked += 1
        if adj is not None:
            previous_adj = adj
    assert checked > 4000
