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

from build_cpi_inflation import (  # noqa: E402
    BLS_SERIES,
    CARRY_FLAG,
    INTERPOLATED_FLAG,
    MONTHLY_FLAG,
    parse_bls_monthly,
)


DATASET = Path("data/processed/cpi_inflation.csv")
PARQUET_DATASET = Path("data/processed/cpi_inflation.parquet")
RAW_BLS = Path(f"sources/raw/cpi_inflation_bls_{BLS_SERIES}.json")
MANIFEST = Path("sources/manifests/cpi_inflation.yml")
CITATION = Path("sources/citations/cpi_inflation.md")

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


def load_raw_bls() -> list[dict]:
    if not RAW_BLS.exists():
        pytest.skip(f"{RAW_BLS} does not exist")
    return json.loads(RAW_BLS.read_text(encoding="utf-8"))


def test_cpi_scaffold_paths_exist():
    assert MANIFEST.exists()
    assert CITATION.exists()


def test_cpi_processed_outputs_exist():
    assert DATASET.exists() and DATASET.stat().st_size > 0
    assert PARQUET_DATASET.exists() and PARQUET_DATASET.stat().st_size > 0


def test_cpi_yahoo_compatible_schema():
    with DATASET.open(newline="", encoding="utf-8") as handle:
        header = next(csv.reader(handle))
    assert header[: len(YAHOO_COLUMNS)] == YAHOO_COLUMNS
    for column in PROJECT_COLUMNS:
        assert column in header


def test_cpi_calendar_daily_coverage_and_unique_sorted_dates():
    rows = read_csv(DATASET)
    dates = [date.fromisoformat(row["Date"]) for row in rows]
    assert dates[0] == date(1970, 1, 1)
    assert dates == sorted(dates)
    assert len(dates) == len(set(dates))
    assert dates[-1] >= date(2026, 6, 1)
    assert all((right - left) == timedelta(days=1) for left, right in zip(dates, dates[1:]))


def test_cpi_levels_positive_and_adj_equals_close():
    rows = read_csv(DATASET)
    for row in rows:
        assert dval(row["Close"]) > 0
        assert row["Adj Close"] == row["Close"]
        assert row["Price Return"] == row["Total Return"]


def test_cpi_returns_recompute_from_levels():
    rows = read_csv(DATASET)
    previous: Decimal | None = None
    for row in rows:
        level = dval(row["Adj Close"])
        if previous is None:
            assert row["Total Return"] == ""
        else:
            expected = level / previous - Decimal("1")
            assert abs(dval(row["Total Return"]) - expected) <= RETURN_TOLERANCE
        previous = level


def test_cpi_month_start_rows_match_raw_bls():
    rows = read_csv(DATASET)
    by_date = {row["Date"]: row for row in rows}
    monthly = parse_bls_monthly(load_raw_bls())
    checked = 0
    for day, value in monthly:
        if day < date(1970, 1, 1) or day.isoformat() not in by_date:
            continue
        row = by_date[day.isoformat()]
        assert row["Quality Flag"] == MONTHLY_FLAG
        assert dval(row["Close"]) == Decimal(str(value))
        checked += 1
    assert checked > 600


def test_cpi_interpolated_and_carry_flags_are_present():
    rows = read_csv(DATASET)
    flags = {row["Quality Flag"] for row in rows}
    assert MONTHLY_FLAG in flags
    assert INTERPOLATED_FLAG in flags
    assert CARRY_FLAG in flags
    assert len([row for row in rows if row["Quality Flag"] == INTERPOLATED_FLAG]) > 19000
