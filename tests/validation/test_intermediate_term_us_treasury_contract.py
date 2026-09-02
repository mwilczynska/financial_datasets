import csv
import json
from datetime import date
from decimal import Decimal
from pathlib import Path

import pytest


DATASET = Path("data/processed/intermediate_term_us_treasury.csv")
PARQUET_DATASET = Path("data/processed/intermediate_term_us_treasury.parquet")
RAW_FED = Path("sources/raw/intermediate_term_us_treasury_fed_nominal_yield_curve.csv")
RAW_VFITX = Path("sources/raw/intermediate_term_us_treasury_yahoo_vfitx_chart.json")
RAW_IEF = Path("sources/raw/intermediate_term_us_treasury_yahoo_ief_chart.json")
MANIFEST = Path("sources/manifests/intermediate_term_us_treasury.yml")

YAHOO_COLUMNS = ["Date", "Open", "High", "Low", "Close", "Adj Close", "Volume"]
PROJECT_COLUMNS = ["Price Return", "Total Return", "Source", "Quality Flag", "Source Notes"]
RETURN_TOLERANCE = Decimal("0.0000000001")


def read_csv(path: Path) -> list[dict[str, str]]:
    if not path.exists():
        pytest.skip(f"{path} does not exist yet")
    with path.open(newline="", encoding="utf-8") as handle:
        return list(csv.DictReader(handle))


def decimal_value(value: str) -> Decimal:
    return Decimal(value)


def chart_adjusted_returns(path: Path) -> dict[str, Decimal]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    result = payload["chart"]["result"][0]
    timestamps = result["timestamp"]
    quote = result["indicators"]["quote"][0]
    adjusted = result["indicators"]["adjclose"][0]["adjclose"]
    from datetime import datetime, timezone

    values = []
    for index, timestamp in enumerate(timestamps):
        if quote["close"][index] is None or adjusted[index] is None:
            continue
        values.append((datetime.fromtimestamp(timestamp, timezone.utc).date().isoformat(), Decimal(str(adjusted[index]))))

    returns = {}
    previous = None
    for day, value in values:
        if previous is not None:
            returns[day] = value / previous - Decimal("1")
        previous = value
    return returns


def test_intermediate_treasury_scaffold_paths_exist():
    assert MANIFEST.exists()
    assert Path("sources/citations/intermediate_term_us_treasury.md").exists()


def test_intermediate_treasury_processed_outputs_exist():
    assert DATASET.exists()
    assert DATASET.stat().st_size > 0
    assert PARQUET_DATASET.exists()
    assert PARQUET_DATASET.stat().st_size > 0


def test_intermediate_treasury_yahoo_compatible_schema():
    with DATASET.open(newline="", encoding="utf-8") as handle:
        header = next(csv.reader(handle))
    assert header[: len(YAHOO_COLUMNS)] == YAHOO_COLUMNS
    for column in PROJECT_COLUMNS:
        assert column in header


def test_intermediate_treasury_coverage_starts_at_1970():
    rows = read_csv(DATASET)
    dates = [date.fromisoformat(row["Date"]) for row in rows]
    assert min(dates) == date(1970, 1, 2)
    assert len(dates) == len(set(dates))
    assert dates == sorted(dates)


def test_intermediate_treasury_levels_positive_and_returns_recompute():
    rows = read_csv(DATASET)
    previous_close = None
    previous_adjusted = None
    for row in rows:
        close = decimal_value(row["Close"])
        adjusted = decimal_value(row["Adj Close"])
        assert close > 0
        assert adjusted > 0
        if previous_close is None:
            assert row["Price Return"] == ""
            assert row["Total Return"] == ""
        else:
            expected_price = close / previous_close - Decimal("1")
            expected_total = adjusted / previous_adjusted - Decimal("1")
            assert abs(decimal_value(row["Price Return"]) - expected_price) <= RETURN_TOLERANCE
            assert abs(decimal_value(row["Total Return"]) - expected_total) <= RETURN_TOLERANCE
        previous_close = close
        previous_adjusted = adjusted


def test_intermediate_treasury_segment_returns_match_raw_yahoo_adjusted_close():
    rows = read_csv(DATASET)
    if not RAW_VFITX.exists() or not RAW_IEF.exists():
        pytest.skip("Raw Yahoo chart payloads are not available")

    vfitx_returns = chart_adjusted_returns(RAW_VFITX)
    ief_returns = chart_adjusted_returns(RAW_IEF)

    checked_vfitx = 0
    checked_ief = 0
    for row in rows:
        if row["Total Return"] == "":
            continue
        if "VFITX" in row["Source"] and row["Date"] in vfitx_returns:
            assert abs(decimal_value(row["Total Return"]) - vfitx_returns[row["Date"]]) <= RETURN_TOLERANCE
            checked_vfitx += 1
        if "IEF" in row["Source"] and row["Date"] in ief_returns:
            assert abs(decimal_value(row["Total Return"]) - ief_returns[row["Date"]]) <= RETURN_TOLERANCE
            checked_ief += 1

    assert checked_vfitx > 2000
    assert checked_ief > 5000


def test_intermediate_treasury_has_fed_modelled_pre_vfitx_segment():
    rows = read_csv(DATASET)
    fed_rows = [
        row
        for row in rows
        if row["Quality Flag"] == "model_fed_yield_curve_8pt5y_par_treasury_total_return"
    ]
    assert RAW_FED.exists()
    assert len(fed_rows) > 4000
    assert fed_rows[0]["Date"] == "1970-01-02"
    assert fed_rows[-1]["Date"] < "1991-11-01"
    assert any(row["Total Return"] != row["Price Return"] for row in fed_rows[1:100])
    assert decimal_value(fed_rows[-1]["Adj Close"]) > decimal_value(fed_rows[0]["Adj Close"]) * Decimal("1.5")
    assert max(decimal_value(row["Adj Close"]) for row in fed_rows) > Decimal("150")
