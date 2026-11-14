"""Contract checks for the AUD/USD, EUR/USD and GBP/USD spot-rate datasets."""

import csv
import json
import sys
from datetime import date
from decimal import Decimal
from pathlib import Path

import pandas as pd
import pytest

SRC = Path(__file__).resolve().parents[2] / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from fx_rates import ECB_START, OUTPUT_COLUMNS, PAIRS, PEG_FLAG, START_DATE  # noqa: E402

RETURN_TOLERANCE = Decimal("0.0000000001")
# (lowest, highest) USD per unit ever plausible for each pair since 1970.
LEVEL_BOUNDS = {"fx_aud_usd": (0.45, 1.55), "fx_eur_usd": (0.50, 1.65), "fx_gbp_usd": (1.00, 2.70)}
# Dated events that fix the quote direction: (date, sign of the foreign currency move against USD).
ORIENTATION = {
    "fx_aud_usd": [("1976-11-29", -1), ("1983-03-08", -1)],  # AUD devaluations
    "fx_eur_usd": [("1985-09-23", 1), ("1978-11-02", -1)],   # Plaza Accord; Carter dollar rescue
    "fx_gbp_usd": [("2016-06-24", -1), ("1992-09-17", -1)],  # EU referendum; ERM exit
}
pytestmark = pytest.mark.parametrize("stem", sorted(PAIRS))


def read_rows(stem: str) -> list[dict[str, str]]:
    with (Path("data/processed") / f"{stem}.csv").open(newline="", encoding="utf-8") as handle:
        reader = csv.DictReader(handle)
        assert reader.fieldnames == OUTPUT_COLUMNS
        return list(reader)


def test_fx_documentation_paths_exist(stem):
    assert (Path("sources/manifests") / f"{stem}.yml").exists()
    assert Path("sources/citations/fx_rates.md").exists()
    assert Path("docs/methodology_fx.md").exists()


def test_fx_dates_start_in_1970_sorted_and_unique(stem):
    dates = [date.fromisoformat(row["Date"]) for row in read_rows(stem)]
    assert dates[0] == START_DATE
    assert dates == sorted(set(dates))
    assert all(day.weekday() < 5 for day in dates)
    assert max((right - left).days for left, right in zip(dates, dates[1:])) <= 10
    for year in range(1970, dates[-1].year):
        assert sum(day.year == year for day in dates) >= 240


def test_fx_levels_are_spot_only_and_in_range(stem):
    low, high = LEVEL_BOUNDS[stem]
    for row in read_rows(stem):
        assert low < float(row["Close"]) < high
        assert row["Adj Close"] == row["Close"]
        assert row["Price Return"] == row["Total Return"]
        assert row["Open"] == row["High"] == row["Low"] == row["Volume"] == ""


def test_fx_returns_recompute_from_levels(stem):
    rows = read_rows(stem)
    assert rows[0]["Total Return"] == ""
    for previous, row in zip(rows, rows[1:]):
        expected = Decimal(row["Close"]) / Decimal(previous["Close"]) - 1
        assert abs(Decimal(row["Total Return"]) - expected) <= RETURN_TOLERANCE
        assert abs(expected) < Decimal("0.2")


def test_fx_segments_follow_the_documented_source_chain(stem):
    pair = PAIRS[stem]
    rows = read_rows(stem)
    for row in rows:
        if row["Date"] >= ECB_START.isoformat():
            assert row["Quality Flag"] == pair.ecb_flag
        elif stem == "fx_aud_usd" and row["Date"] < "1971-01-04":
            assert row["Quality Flag"] == PEG_FLAG
        else:
            assert row["Quality Flag"] == pair.bis_flag
    modeled = [row for row in rows if row["Quality Flag"].startswith("model_")]
    assert len(modeled) == (251 if stem == "fx_aud_usd" else 0)


def test_fx_quote_direction_matches_dated_events(stem):
    returns = {row["Date"]: row["Total Return"] for row in read_rows(stem)}
    for day, sign in ORIENTATION[stem]:
        assert float(returns[day]) * sign > 0.03


def test_fx_splices_are_continuous(stem):
    returns = {row["Date"]: float(row["Total Return"]) for row in read_rows(stem) if row["Total Return"]}
    assert abs(returns["1999-01-04"]) < 0.015
    assert abs(returns["1971-01-04"]) < 0.002


def test_fx_modeled_1970_aud_tracks_sterling(stem):
    if stem != "fx_aud_usd":
        return
    aud = {row["Date"]: row["Total Return"] for row in read_rows("fx_aud_usd") if row["Date"] < "1971-01-01"}
    gbp = {row["Date"]: row["Total Return"] for row in read_rows("fx_gbp_usd") if row["Date"] < "1971-01-01"}
    assert aud.keys() == gbp.keys()
    assert all(abs(float(aud[day] or 0) - float(gbp[day] or 0)) < 1e-9 for day in aud)
    levels = [float(row["Close"]) for row in read_rows("fx_aud_usd") if row["Date"] < "1971-01-01"]
    assert 1.10 < min(levels) and max(levels) < 1.13  # official parity was USD 1.12


def test_fx_parquet_and_build_metadata_match_csv(stem):
    rows = read_rows(stem)
    frame = pd.read_parquet(Path("data/processed") / f"{stem}.parquet")
    assert list(frame.columns) == OUTPUT_COLUMNS and len(frame) == len(rows)
    assert pd.to_datetime(frame["Date"]).dt.strftime("%Y-%m-%d").tolist() == [row["Date"] for row in rows]
    assert all(abs(left - float(row["Close"])) < 1e-12 for left, row in zip(frame["Close"], rows))
    metadata = json.loads((Path("sources/manifests") / f"{stem}_build.json").read_text(encoding="utf-8"))
    assert metadata["row_count"] == len(rows)
    assert (metadata["first_date"], metadata["last_date"]) == (rows[0]["Date"], rows[-1]["Date"])
    assert metadata["bis_ecb_overlap"]["days"] >= 200
    assert float(metadata["bis_ecb_overlap"]["max_relative_difference"]) < 1e-5
