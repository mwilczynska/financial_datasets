import csv
import zipfile
from datetime import date, timedelta
from decimal import Decimal
from pathlib import Path

import pytest


DATASET = Path("data/processed/us_large_cap_sp500.csv")
FRED_FIXTURE = Path("tests/fixtures/fred_sp500_sample.csv")
ANNUAL_CHECK_FIXTURE = Path("tests/fixtures/us_large_cap_annual_check_1970_1987.csv")
KEN_FRENCH_DAILY_ZIP = Path("sources/raw/Portfolios_Formed_on_ME_daily_CSV.zip")
PARQUET_DATASET = Path("data/processed/us_large_cap_sp500.parquet")

YAHOO_COLUMNS = ["Date", "Open", "High", "Low", "Close", "Adj Close", "Volume"]
PROJECT_COLUMNS = ["Price Return", "Total Return", "Source", "Quality Flag", "Source Notes"]
MIN_START_DATE = date(1970, 1, 1)
MAX_START_LAG_DAYS = 7
RETURN_TOLERANCE = Decimal("0.0000000001")
SOURCE_TOLERANCE = Decimal("0.01")
FIRST_ADJUSTED_DATE = date(1970, 1, 2)
SP500TR_RETURN_START_DATE = date(1988, 1, 5)
ANNUAL_SANITY_MAX_DIFF_PCT_POINTS = Decimal("5.0")
ANNUAL_SANITY_MEAN_DIFF_PCT_POINTS = Decimal("2.0")


def read_csv(path: Path) -> list[dict[str, str]]:
    if not path.exists():
        pytest.skip(f"{path} does not exist yet")
    with path.open(newline="", encoding="utf-8") as handle:
        return list(csv.DictReader(handle))


def decimal_value(value: str) -> Decimal:
    return Decimal(value)


def load_ken_french_hi30_returns() -> dict[str, Decimal]:
    if not KEN_FRENCH_DAILY_ZIP.exists():
        pytest.skip(f"{KEN_FRENCH_DAILY_ZIP} does not exist")

    with zipfile.ZipFile(KEN_FRENCH_DAILY_ZIP) as archive:
        text = archive.read("Portfolios_Formed_on_ME_daily.csv").decode("utf-8", errors="replace")

    lines = text.splitlines()
    header_index = next(
        index for index, line in enumerate(lines) if "Average Value Weighted Returns -- Daily" in line
    ) + 1
    header = [column.strip() for column in lines[header_index].split(",")]
    hi30_index = header.index("Hi 30")

    returns: dict[str, Decimal] = {}
    for line in lines[header_index + 1 :]:
        if not line.strip():
            break
        parts = [part.strip() for part in line.split(",")]
        raw_date = parts[0]
        if not raw_date.isdigit() or len(raw_date) != 8:
            break
        returns[f"{raw_date[:4]}-{raw_date[4:6]}-{raw_date[6:8]}"] = Decimal(parts[hi30_index]) / Decimal("100")
    return returns


def test_validation_scaffold_paths_exist():
    assert Path("docs/source_registry.md").exists()
    assert Path("docs/validation.md").exists()
    assert Path("sources/manifests/us_large_cap_sp500.yml").exists()


def test_processed_outputs_exist():
    assert DATASET.exists()
    assert DATASET.stat().st_size > 0
    assert PARQUET_DATASET.exists()
    assert PARQUET_DATASET.stat().st_size > 0


def test_yahoo_compatible_schema():
    with DATASET.open(newline="", encoding="utf-8") as handle:
        reader = csv.reader(handle)
        header = next(reader)

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


def test_positive_levels_when_present():
    rows = read_csv(DATASET)

    for row in rows:
        for column in ["Close", "Adj Close"]:
            if row[column]:
                assert decimal_value(row[column]) > 0


def test_price_return_recomputes_from_close():
    rows = read_csv(DATASET)
    previous_close: Decimal | None = None

    for row in rows:
        close = decimal_value(row["Close"])
        if previous_close is None:
            assert row["Price Return"] == ""
        else:
            expected = close / previous_close - Decimal("1")
            actual = decimal_value(row["Price Return"])
            assert abs(actual - expected) <= RETURN_TOLERANCE
        previous_close = close


def test_adjusted_close_uses_total_return_source_when_available():
    rows = read_csv(DATASET)

    adjusted_rows = [row for row in rows if row["Adj Close"]]
    assert len(adjusted_rows) == len(rows)
    assert date.fromisoformat(adjusted_rows[0]["Date"]) == FIRST_ADJUSTED_DATE
    assert decimal_value(adjusted_rows[0]["Adj Close"]) == decimal_value(adjusted_rows[0]["Close"])
    assert adjusted_rows[0]["Total Return"] == ""

    for row in rows:
        row_date = date.fromisoformat(row["Date"])
        assert row["Adj Close"] != ""
        if row_date < SP500TR_RETURN_START_DATE:
            assert row["Quality Flag"] == "observed_price_index_crsp_large_cap_total_return"
            assert "Kenneth French/CRSP Hi 30" in row["Source Notes"]
        else:
            assert row["Quality Flag"] == "observed_price_index_sp500_total_return"
            assert "^SP500TR" in row["Source Notes"]


def test_total_return_recomputes_from_adjusted_close():
    rows = read_csv(DATASET)
    previous_adjusted: Decimal | None = None

    for row in rows:
        if not row["Adj Close"]:
            previous_adjusted = None
            continue

        adjusted = decimal_value(row["Adj Close"])
        if previous_adjusted is None:
            assert row["Total Return"] == ""
        else:
            expected = adjusted / previous_adjusted - Decimal("1")
            actual = decimal_value(row["Total Return"])
            assert abs(actual - expected) <= RETURN_TOLERANCE
        previous_adjusted = adjusted


def test_pre_sp500tr_daily_total_return_matches_ken_french_hi30_source():
    rows = read_csv(DATASET)
    french_returns = load_ken_french_hi30_returns()

    checked = 0
    for row in rows:
        row_date = date.fromisoformat(row["Date"])
        if row_date <= FIRST_ADJUSTED_DATE or row_date >= SP500TR_RETURN_START_DATE:
            continue

        expected = french_returns.get(row["Date"])
        assert expected is not None
        actual = decimal_value(row["Total Return"])
        assert abs(actual - expected) <= RETURN_TOLERANCE
        checked += 1

    assert checked > 4000


def test_pre_sp500tr_annual_returns_are_reasonable_against_external_sp500_reference():
    rows = read_csv(ANNUAL_CHECK_FIXTURE)
    diffs = [abs(decimal_value(row["Diff_Pct_Points"])) for row in rows]

    assert max(diffs) <= ANNUAL_SANITY_MAX_DIFF_PCT_POINTS
    assert sum(diffs) / Decimal(len(diffs)) <= ANNUAL_SANITY_MEAN_DIFF_PCT_POINTS


def test_recent_close_matches_fred_fixture_when_available():
    rows = read_csv(DATASET)
    fred_rows = read_csv(FRED_FIXTURE)

    candidate = {row["Date"]: decimal_value(row["Close"]) for row in rows}
    for fred_row in fred_rows:
        assert fred_row["Date"] in candidate
        diff = abs(candidate[fred_row["Date"]] - decimal_value(fred_row["Close"]))
        assert diff <= SOURCE_TOLERANCE
