"""CMDTY's published schema, direct GSCI import, provenance, and splice contracts."""
import csv
import hashlib
import io
import json
import subprocess
from datetime import date, datetime, timedelta, timezone
from decimal import Decimal
from pathlib import Path

import pandas as pd
import pytest

from src import build_broad_commodities as builder
from src import gsci_daily

ROOT = Path(__file__).resolve().parents[2]
DATASET = ROOT / "data/processed/broad_commodities.csv"
PARQUET_DATASET = DATASET.with_suffix(".parquet")
BUILD_MANIFEST = ROOT / "sources/manifests/broad_commodities_build.json"
RETURN_TOLERANCE = Decimal("1e-10")


@pytest.fixture(scope="module")
def rows():
    return builder.read_csv(DATASET)


@pytest.fixture(scope="module")
def metadata():
    return json.loads(BUILD_MANIFEST.read_text(encoding="utf-8"))


@pytest.fixture(scope="module")
def daily():
    path = ROOT / "sources/raw" / gsci_daily.RAW_FILE
    if not path.exists():
        pytest.skip("Pinned raw workbook is a local cache; acquire it with the CMDTY builder")
    return gsci_daily.load_snapshot(path)


@pytest.fixture(scope="module")
def baseline(metadata):
    if "gsci_migration" not in metadata:
        assert {"^BCOM", "^IRX", "DBC"} <= metadata["raw_sources"].keys()
        pytest.skip("Raw-source full rebuild: migration-baseline checks do not apply")
    reference = metadata["gsci_migration"]["baseline"]
    archive = ROOT / reference["local_archive"]
    if archive.exists():
        payload = archive.read_bytes()
    else:
        result = subprocess.run(["git", "show", f"{reference['git_commit']}:{reference['csv_path']}"],
                                cwd=ROOT, capture_output=True)
        if result.returncode:
            pytest.skip("Migration baseline requires full Git history or its local archive")
        payload = result.stdout
    assert hashlib.sha256(payload).hexdigest() == reference["csv_sha256"]
    return list(csv.DictReader(io.StringIO(payload.decode("utf-8"))))


def test_broad_commodities_scaffold_paths_exist():
    for relative in ("sources/manifests/broad_commodities.yml", "sources/citations/broad_commodities.md",
                     gsci_daily.CALENDAR_FILE, gsci_daily.CALENDAR_MANIFEST):
        assert (ROOT / relative).is_file()


def test_broad_commodities_processed_outputs_and_metadata_agree(rows, metadata):
    assert DATASET.is_file() and PARQUET_DATASET.is_file()
    assert metadata["row_count"] == len(rows)
    assert metadata["first_date"] == rows[0]["Date"] == "1970-01-02"
    assert metadata["last_date"] == rows[-1]["Date"]
    assert metadata["csv_sha256"] == builder.checksum(DATASET)
    assert metadata["parquet_sha256"] == builder.checksum(PARQUET_DATASET)
    assert pd.read_csv(DATASET, parse_dates=["Date"]).equals(pd.read_parquet(PARQUET_DATASET))


def test_broad_commodities_yahoo_compatible_schema():
    with DATASET.open(newline="", encoding="utf-8") as handle:
        assert next(csv.reader(handle)) == builder.OUTPUT_COLUMNS


def test_broad_commodities_positive_levels_and_return_arithmetic(rows):
    assert [row["Date"] for row in rows] == sorted({row["Date"] for row in rows})
    previous = None
    for row in rows:
        levels = [Decimal(row[key]) for key in ("Close", "Adj Close")]
        assert all(level.is_finite() and level > 0 for level in levels)
        if previous is None:
            assert levels == [Decimal(100), Decimal(100)]
            assert row["Price Return"] == row["Total Return"] == ""
        else:
            for index, key in enumerate(("Price Return", "Total Return")):
                assert abs(Decimal(row[key]) - (levels[index] / previous[index] - 1)) <= RETURN_TOLERANCE
        previous = levels


def test_broad_commodities_cumulative_tr_growth_exceeds_er_growth(rows):
    # This is a cumulative level check, not a ban on rounded negative daily TR-ER spreads.
    assert all(Decimal(row["Adj Close"]) >= Decimal(row["Close"]) - Decimal("0.000001") for row in rows)


def test_every_gsci_level_matches_the_pinned_paired_daily_source(rows, daily):
    source = {row["Date"]: row for row in daily}
    calendar = gsci_daily.load_calendar(ROOT)
    early = [row for row in rows if row["Date"] <= "1991-01-02"]
    assert len(early) == 5255
    assert [row["Date"] for row in early] == calendar
    for row in early:
        assert row["Quality Flag"] == builder.GSCI_FLAG
        for output, raw in (("Close", "GSCI_ER"), ("Adj Close", "GSCI_TR")):
            expected = 100 * source[row["Date"]][raw] / source["1970-01-02"][raw]
            assert abs(Decimal(row[output]) - expected) <= Decimal("5e-11")
        assert all(row[key] == "" for key in ("Open", "High", "Low", "Volume"))
    assert early[-1]["Close"] == "458.48"
    assert early[-1]["Adj Close"] == "2346.026"
    # Check both return types on sampled level dates, including skipped source dates.
    for prior, row in zip(early, early[1:]):
        for key, raw in (("Price Return", "GSCI_ER"), ("Total Return", "GSCI_TR")):
            expected = source[row["Date"]][raw] / source[prior["Date"]][raw] - 1
            assert abs(Decimal(row[key]) - expected) <= RETURN_TOLERANCE


def test_published_gsci_reference_gates(daily, metadata):
    checks = gsci_daily.published_reference_checks(daily)
    assert checks["annual_tr_checks_passed"] == 22
    assert checks["sec_tr_level_checks_passed"] == 22
    assert checks["max_annual_error_percentage_points"] < 0.005
    assert checks["max_sec_level_error"] < 0.005
    assert metadata["raw_sources"]["GSCI_ER_TR"]["reference_checks"] == checks


def test_gsci_provenance_and_fill_qualification(rows, metadata):
    source = metadata["raw_sources"]["GSCI_ER_TR"]
    assert source["sha256"] == gsci_daily.SHA256
    assert source["commit"] == gsci_daily.COMMIT
    assert source["source_columns"] == {"Close": "GSCI_ER", "Adj Close": "GSCI_TR"}
    assert source["observed_rows"] == 14609
    assert source["index_launch_date"] == "1991-05-01"
    assert "PREVIOUS_VALUE" in source["fill"]
    assert "No verified grant" in source["redistribution_rights"]
    for row in rows:
        if row["Quality Flag"] == builder.GSCI_FLAG:
            notes = row["Source Notes"].lower()
            assert "back-calculated" in notes and "holidays" in notes and "1991-05-01" in notes


def test_gsci_calendar_is_unchanged_from_versioned_baseline(rows, baseline):
    assert [row["Date"] for row in rows if row["Date"] <= "1991-01-02"] == [
        row["Date"] for row in baseline if row["Date"] <= "1991-01-02"]


def test_migration_preserves_later_historical_returns_and_splices(rows, baseline, metadata):
    new = {row["Date"]: row for row in rows}
    # Ordinary updates can revise their recent DBC overlap. When no update has
    # followed migration, check every original row. Later runs always check the
    # frozen portion preceding the original 14-day update window.
    after_migration = metadata.get("last_incremental_update_utc", "") > metadata["gsci_migration"]["timestamp_utc"]
    limit = (date.fromisoformat(baseline[-1]["Date"]) - timedelta(days=15)).isoformat() if after_migration else baseline[-1]["Date"]
    checked = 0
    for index, old in enumerate(baseline):
        if not "1991-01-02" < old["Date"] <= limit:
            continue
        current, previous = new[old["Date"]], new[baseline[index - 1]["Date"]]
        for column in ("Price Return", "Total Return", "Quality Flag"):
            assert current[column] == old[column]
        for column in ("Close", "Adj Close"):
            old_ratio = Decimal(old[column]) / Decimal(baseline[index - 1][column])
            new_ratio = Decimal(current[column]) / Decimal(previous[column])
            assert abs(new_ratio - old_ratio) < RETURN_TOLERANCE
        checked += 1
    assert checked > 8900
    for day, prior, flag in (("1991-01-03", "1991-01-02", builder.BCOM_FLAG),
                             ("2006-02-07", "2006-02-06", builder.DBC_FLAG)):
        assert new[day]["Quality Flag"] == flag
        recorded = metadata["gsci_migration"]["splice_checks"][day]
        assert recorded["prior_date"] == prior
        for column in ("Close", "Adj Close"):
            actual = Decimal(new[day][column]) / Decimal(new[prior][column]) - 1
            assert abs(actual - Decimal(recorded[column]["baseline_return"])) < RETURN_TOLERANCE


def test_quality_flags_and_segment_counts(rows, metadata):
    flags = {row["Quality Flag"] for row in rows}
    assert flags == {builder.GSCI_FLAG, builder.BCOM_FLAG, builder.DBC_FLAG}
    counts = {flag: sum(row["Quality Flag"] == flag for row in rows) for flag in flags}
    assert counts[builder.GSCI_FLAG] == 5255
    assert counts[builder.BCOM_FLAG] == 3781
    assert counts[builder.DBC_FLAG] > 5000
    assert metadata["segment_row_counts"] == counts


@pytest.mark.parametrize("stem,flag,columns", [
    ("bcom", builder.BCOM_FLAG, (("Close", "Price Return"),)),
    ("dbc", builder.DBC_FLAG, (("Close", "Price Return"), ("Adj Close", "Total Return"))),
])
def test_later_returns_match_historical_yahoo_cache_if_available(rows, stem, flag, columns):
    path = ROOT / f"sources/raw/broad_commodities_yahoo_{stem}_chart.json"
    if not path.exists():
        pytest.skip(f"Full historical {stem} raw chart is unavailable; baseline preservation is checked separately")
    raw = builder.chart_rows(json.loads(path.read_text(encoding="utf-8")))
    expected = {}
    for prior, current in zip(raw, raw[1:]):
        expected[current["Date"]] = {out: Decimal(str(current[key])) / Decimal(str(prior[key])) - 1
                                     for key, out in columns}
    checked = 0
    for row in rows:
        if row["Quality Flag"] == flag and row["Date"] in expected:
            for _, output in columns:
                assert abs(Decimal(row[output]) - expected[row["Date"]][output]) < RETURN_TOLERANCE
            checked += 1
    assert checked > (3500 if stem == "bcom" else 4500)


def valid_bcom_cache(tmp_path):
    day, last = date(1991, 1, 2), date(2006, 2, 6)
    days = []
    while day <= last:
        if day.weekday() < 5:
            days.append(day)
        day += timedelta(days=1)
    payload = {"chart": {"result": [{
        "meta": {"symbol": "^BCOM", "exchangeTimezoneName": "UTC"},
        "timestamp": [int(datetime.combine(day, datetime.min.time(), timezone.utc).timestamp()) for day in days],
        "indicators": {"quote": [{"close": [100.0] * len(days)}]},
    }]}}
    path = tmp_path / "broad_commodities_yahoo_bcom_chart.json"
    path.write_text(json.dumps(payload), encoding="utf-8")
    return path


def test_valid_historical_cache_avoids_live_request(tmp_path, monkeypatch):
    valid_bcom_cache(tmp_path)
    def unexpected(*args, **kwargs):
        raise AssertionError("A validated historical cache must avoid a live request")
    monkeypatch.setattr(builder, "fetch_chart", unexpected)
    _, mode = builder.load_historical_chart(tmp_path, "^BCOM", date(2026, 9, 30))
    assert mode == "cached"


def test_historical_refresh_failure_preserves_valid_cache(tmp_path, monkeypatch):
    path = valid_bcom_cache(tmp_path)
    original = path.read_bytes()
    def unavailable(*args, **kwargs):
        raise builder.requests.HTTPError("404 Not Found")
    monkeypatch.setattr(builder, "fetch_chart", unavailable)
    _, mode = builder.load_historical_chart(tmp_path, "^BCOM", date(2026, 9, 30), refresh=True)
    assert mode == "cached_after_fetch_error"
    assert path.read_bytes() == original


def test_historical_bcom_rejects_incomplete_cache(tmp_path, monkeypatch):
    path = valid_bcom_cache(tmp_path)
    payload = json.loads(path.read_text(encoding="utf-8"))
    payload["chart"]["result"][0]["timestamp"] = []
    path.write_text(json.dumps(payload), encoding="utf-8")
    def unavailable(*args, **kwargs):
        raise builder.requests.HTTPError("404 Not Found")
    monkeypatch.setattr(builder, "fetch_chart", unavailable)
    with pytest.raises(RuntimeError, match="no valid cache"):
        builder.load_historical_chart(tmp_path, "^BCOM", date(2026, 9, 30))
