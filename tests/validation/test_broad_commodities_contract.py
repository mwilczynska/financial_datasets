import csv
import json
import math
import statistics
from datetime import date
from decimal import Decimal
from pathlib import Path

import pytest


DATASET = Path("data/processed/broad_commodities.csv")
PARQUET_DATASET = Path("data/processed/broad_commodities.parquet")
RAW_SPGSCI = Path("sources/raw/broad_commodities_yahoo_spgsci_chart.json")
RAW_BCOM = Path("sources/raw/broad_commodities_yahoo_bcom_chart.json")
RAW_DBC = Path("sources/raw/broad_commodities_yahoo_dbc_chart.json")
RAW_IRX = Path("sources/raw/broad_commodities_yahoo_irx_chart.json")
GSCI_ANCHOR = Path("sources/raw/broad_commodities_gsci_tr_macromicro.csv")
MANIFEST = Path("sources/manifests/broad_commodities.yml")

YAHOO_COLUMNS = ["Date", "Open", "High", "Low", "Close", "Adj Close", "Volume"]
PROJECT_COLUMNS = ["Price Return", "Total Return", "Source", "Quality Flag", "Source Notes"]
RETURN_TOLERANCE = Decimal("0.0000000001")

GSCI_SMOOTHED_FLAG = "model_gsci_total_return_anchor_smoothed_daily"
GSCI_SHAPE_FLAG = "model_gsci_total_return_anchor_with_spgsci_spot_daily_shape"
BCOM_FLAG = "model_bcom_excess_return_plus_tbill_collateral"
DBC_FLAG = "observed_yahoo_dbc_dblci_total_return_etf"


def read_csv(path: Path) -> list[dict[str, str]]:
    if not path.exists():
        pytest.skip(f"{path} does not exist yet")
    with path.open(newline="", encoding="utf-8") as handle:
        return list(csv.DictReader(handle))


def decimal_value(value: str) -> Decimal:
    return Decimal(value)


def chart_close_returns(path: Path, use_adj: bool = False) -> dict[str, Decimal]:
    """Compute daily returns from raw Yahoo chart JSON (close or adj close)."""
    payload = json.loads(path.read_text(encoding="utf-8"))
    result = payload["chart"]["result"][0]
    timestamps = result["timestamp"]
    quote = result["indicators"]["quote"][0]
    adj_list = result.get("indicators", {}).get("adjclose", [{}])[0].get("adjclose", [])

    from datetime import datetime, timezone

    values = []
    for index, timestamp in enumerate(timestamps):
        close = quote["close"][index]
        adj = adj_list[index] if index < len(adj_list) else close
        if close is None:
            continue
        raw_val = adj if use_adj else close
        if raw_val is None:
            raw_val = close
        values.append((datetime.fromtimestamp(timestamp, timezone.utc).date().isoformat(), Decimal(str(raw_val))))

    returns = {}
    previous = None
    for day, value in values:
        if previous is not None:
            returns[day] = value / previous - Decimal("1")
        previous = value
    return returns


def gsci_anchor_levels() -> dict[str, float]:
    if not GSCI_ANCHOR.exists():
        pytest.skip("S&P GSCI Total Return anchor not available")
    out = {}
    with GSCI_ANCHOR.open(newline="", encoding="utf-8") as handle:
        for row in csv.DictReader(handle):
            out[row["Date"]] = float(row["GSCI_TR_Index"])
    return out


def test_broad_commodities_scaffold_paths_exist():
    assert MANIFEST.exists()
    assert Path("sources/citations/broad_commodities.md").exists()
    assert GSCI_ANCHOR.exists(), "Static S&P GSCI Total Return anchor must be committed"


def test_broad_commodities_processed_outputs_exist():
    assert DATASET.exists()
    assert DATASET.stat().st_size > 0
    assert PARQUET_DATASET.exists()
    assert PARQUET_DATASET.stat().st_size > 0


def test_broad_commodities_yahoo_compatible_schema():
    with DATASET.open(newline="", encoding="utf-8") as handle:
        header = next(csv.reader(handle))
    assert header[: len(YAHOO_COLUMNS)] == YAHOO_COLUMNS
    for column in PROJECT_COLUMNS:
        assert column in header


def test_broad_commodities_coverage_starts_at_1970():
    rows = read_csv(DATASET)
    dates = [date.fromisoformat(row["Date"]) for row in rows]
    # Coverage starts 1970-01-02 via the S&P GSCI Total Return anchor on ^IRX trading dates.
    assert min(dates) == date(1970, 1, 2)
    assert len(dates) == len(set(dates)), "Duplicate dates found"
    assert dates == sorted(dates), "Dates are not sorted"


def test_broad_commodities_levels_positive_and_returns_recompute():
    rows = read_csv(DATASET)
    previous_close = None
    previous_adjusted = None
    for row in rows:
        close = decimal_value(row["Close"])
        adjusted = decimal_value(row["Adj Close"])
        assert close > 0, f"Close not positive on {row['Date']}"
        assert adjusted > 0, f"Adj Close not positive on {row['Date']}"
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


def test_broad_commodities_total_return_is_collateralized_excess_return():
    """Adj Close (total return) must always be >= Close (excess return); collateral is non-negative."""
    rows = read_csv(DATASET)
    for row in rows:
        assert decimal_value(row["Adj Close"]) >= decimal_value(row["Close"]) - Decimal("0.000001"), (
            f"Adj Close (TR) below Close (ER) on {row['Date']}"
        )


def test_broad_commodities_dbc_segment_returns_match_raw_yahoo():
    rows = read_csv(DATASET)
    if not RAW_DBC.exists():
        pytest.skip("Raw DBC chart payload not available")

    dbc_adj_returns = chart_close_returns(RAW_DBC, use_adj=True)
    dbc_close_returns = chart_close_returns(RAW_DBC, use_adj=False)

    checked = 0
    for row in rows:
        if row["Quality Flag"] != DBC_FLAG or row["Total Return"] == "":
            continue
        if row["Date"] in dbc_adj_returns:
            assert abs(decimal_value(row["Total Return"]) - dbc_adj_returns[row["Date"]]) <= RETURN_TOLERANCE, (
                f"DBC total return mismatch on {row['Date']}"
            )
        if row["Date"] in dbc_close_returns:
            assert abs(decimal_value(row["Price Return"]) - dbc_close_returns[row["Date"]]) <= RETURN_TOLERANCE, (
                f"DBC price return mismatch on {row['Date']}"
            )
            checked += 1

    assert checked > 4000, f"Too few DBC rows checked: {checked}"


def test_broad_commodities_bcom_price_returns_match_raw_yahoo():
    rows = read_csv(DATASET)
    if not RAW_BCOM.exists():
        pytest.skip("Raw BCOM chart payload not available")

    # For ^BCOM, Close (price return) is the raw excess-return index return (no collateral).
    bcom_returns = chart_close_returns(RAW_BCOM, use_adj=False)

    checked = 0
    for row in rows:
        if row["Quality Flag"] != BCOM_FLAG or row["Price Return"] == "":
            continue
        if row["Date"] in bcom_returns:
            assert abs(decimal_value(row["Price Return"]) - bcom_returns[row["Date"]]) <= RETURN_TOLERANCE, (
                f"BCOM price return mismatch on {row['Date']}"
            )
            checked += 1

    assert checked > 3000, f"Too few BCOM rows checked: {checked}"


def test_broad_commodities_gsci_anchor_segment_present_and_growing():
    """Segment 0 is the GSCI TR anchor, smoothed; Adj Close grows with roll + collateral."""
    rows = read_csv(DATASET)
    model_rows = [r for r in rows if r["Quality Flag"] == GSCI_SMOOTHED_FLAG]

    assert len(model_rows) > 3000, f"Too few GSCI-smoothed rows: {len(model_rows)}"
    assert model_rows[0]["Date"] == "1970-01-02"
    assert model_rows[-1]["Date"] < "1984-01-05"
    # First row has no return
    assert model_rows[0]["Price Return"] == ""
    assert model_rows[0]["Total Return"] == ""
    for row in model_rows[:50]:
        notes = row["Source Notes"].lower()
        assert "gsci" in notes and "total return" in notes
        assert "smoothed" in notes
        assert "roll" in notes

    # Adj Close (total return) at the end of Segment 0 should be well above the start
    # (the 1970s commodity boom + high T-bill collateral lifts the GSCI TR well over 1.5x).
    start_adj = decimal_value(model_rows[0]["Adj Close"])
    end_adj = decimal_value(model_rows[-1]["Adj Close"])
    assert end_adj / start_adj > Decimal("1.5"), f"GSCI TR segment growth too low: {start_adj} -> {end_adj}"
    # Adj Close (TR) outgrows Close (ER) because of T-bill collateral.
    end_close = decimal_value(model_rows[-1]["Close"])
    assert end_adj > end_close * Decimal("1.3"), "Collateral should lift Adj Close well above Close"


def test_broad_commodities_adj_close_tracks_gsci_anchor():
    """Adj Close must track the S&P GSCI Total Return anchor through the reconstructed era."""
    rows = read_csv(DATASET)
    adj = {r["Date"]: float(r["Adj Close"]) for r in rows}
    anchor = gsci_anchor_levels()
    # Both series are base 100 at 1970-01-02, so the ratio should hover near 1.0.
    ratios = [adj[d] / v for d, v in anchor.items() if d in adj and d < "1991-01-03"]
    assert len(ratios) > 100, f"Too few anchor sample dates matched: {len(ratios)}"
    assert max(abs(r - 1.0) for r in ratios) < 0.05, (
        f"Adj Close drifts from GSCI TR anchor: ratio range {min(ratios):.4f}..{max(ratios):.4f}"
    )


def test_broad_commodities_spgsci_shape_segment_is_desmoothed():
    """Segment 1 (1984-1991) carries genuine daily volatility from the ^SPGSCI spot shape.

    The pre-2026 fix smoothed this era to ~zero within-period volatility. The overlay onto the
    daily ^SPGSCI spot shape must restore realistic commodity volatility while the level still
    tracks the GSCI TR anchor (verified separately). Also checks the collateral relationship.
    """
    rows = read_csv(DATASET)
    shape_rows = [r for r in rows if r["Quality Flag"] == GSCI_SHAPE_FLAG]

    assert len(shape_rows) > 1500, f"Too few GSCI-shape rows: {len(shape_rows)}"
    assert shape_rows[0]["Date"] >= "1984-01-04"
    assert shape_rows[-1]["Date"] < "1991-02-01"

    total_returns = [float(r["Total Return"]) for r in shape_rows if r["Total Return"]]
    annualized_vol = statistics.pstdev(total_returns) * math.sqrt(252)
    assert annualized_vol > 0.08, f"Segment 1 still looks smoothed: annualized vol={annualized_vol:.4f}"

    # Internal collateral growth: (Adj/Close) should rise over the ~7-year, high-rate segment.
    start_ratio = float(shape_rows[0]["Adj Close"]) / float(shape_rows[0]["Close"])
    end_ratio = float(shape_rows[-1]["Adj Close"]) / float(shape_rows[-1]["Close"])
    assert end_ratio / start_ratio > 1.3, (
        f"T-bill collateral growth in Segment 1 too low: {start_ratio:.3f} -> {end_ratio:.3f}"
    )


def test_broad_commodities_quality_flag_counts():
    rows = read_csv(DATASET)
    smooth_count = sum(1 for r in rows if r["Quality Flag"] == GSCI_SMOOTHED_FLAG)
    shape_count = sum(1 for r in rows if r["Quality Flag"] == GSCI_SHAPE_FLAG)
    bcom_count = sum(1 for r in rows if r["Quality Flag"] == BCOM_FLAG)
    dbc_count = sum(1 for r in rows if r["Quality Flag"] == DBC_FLAG)
    assert smooth_count > 3000
    assert shape_count > 1500
    assert bcom_count > 3500
    assert dbc_count > 4500
    assert smooth_count + shape_count + bcom_count + dbc_count == len(rows)
