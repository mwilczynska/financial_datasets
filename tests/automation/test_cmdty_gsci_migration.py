"""Daily-source selection, independent splices, and safe CMDTY migration."""
from __future__ import annotations

from copy import deepcopy
import json
from decimal import Decimal
from datetime import date, timedelta
from pathlib import Path

import pandas as pd
import pytest

from src import build_broad_commodities as builder
from src import gsci_daily
from src import incremental_update


def fixture_history():
    calendar = ["1970-01-02", "1970-01-05", "1970-01-07", "1970-01-08", "1991-01-02"]
    daily = [
        {"Date": day, "GSCI_ER": Decimal(er), "GSCI_TR": Decimal(tr)}
        for day, er, tr in [
            ("1970-01-02", "100", "100"), ("1970-01-05", "110", "120"),
            ("1970-01-06", "1000", "1200"), ("1970-01-07", "121", "144"),
            ("1970-01-08", "121", "144"), ("1991-01-02", "300", "900"),
        ]
    ]
    levels = [(100, 100), (101, 102), (102, 104), (102, 104), (125, 180),
              (137.5, 198.54), (165, 250), (181.5, 260), (180, 259)]
    dates = calendar + ["1991-01-03", "2006-02-06", "2006-02-07", "2006-02-08"]
    rows = []
    previous = None
    for index, (day, values) in enumerate(zip(dates, levels)):
        close, tr = (Decimal(str(value)) for value in values)
        flag = "model_gsci_total_return_anchor_smoothed_daily" if index < 5 else builder.BCOM_FLAG if index < 7 else builder.DBC_FLAG
        rows.append({"Date": day, "Open": "", "High": "", "Low": "", "Close": str(close),
                     "Adj Close": str(tr), "Volume": "",
                     "Price Return": "" if previous is None else f"{close / previous[0] - 1:.10f}",
                     "Total Return": "" if previous is None else f"{tr / previous[1] - 1:.10f}",
                     "Source": "Fixture source", "Quality Flag": flag, "Source Notes": "Fixture notes"})
        previous = close, tr
    return rows, daily, calendar


def test_levels_selected_before_returns_and_flat_rows_kept():
    _, daily, calendar = fixture_history()
    rows = builder.gsci_rows(daily, calendar)
    selected = {row["Date"]: row for row in rows}
    assert [row["Date"] for row in rows] == calendar
    # The unselected January 6 spike must not become January 7's denominator.
    assert Decimal(selected["1970-01-07"]["Price Return"]) == Decimal("0.1")
    assert Decimal(selected["1970-01-07"]["Total Return"]) == Decimal("0.2")
    assert selected["1970-01-08"]["Price Return"] == "0"
    assert rows[-1]["Close"] == "300" and rows[-1]["Adj Close"] == "900"


def test_migration_separately_scales_er_tr_and_preserves_every_tail_return():
    old, daily, calendar = fixture_history()
    baseline = deepcopy(old)
    new, checks = builder.replace_gsci_prefix(old, daily, calendar)
    assert old == baseline, "Migration must not mutate its baseline"
    assert [row["Date"] for row in new] == [row["Date"] for row in old]
    assert Decimal(checks["level_scale_factors"]["Close"]) == Decimal("2.4")
    assert Decimal(checks["level_scale_factors"]["Adj Close"]) == Decimal("5")
    assert checks["later_return_columns_unchanged"]
    for index in range(5, len(old)):
        for column in ("Close", "Adj Close"):
            prior_ratio = Decimal(old[index][column]) / Decimal(old[index - 1][column])
            new_ratio = Decimal(new[index][column]) / Decimal(new[index - 1][column])
            assert abs(prior_ratio - new_ratio) < Decimal("1e-10")
        for column in ("Price Return", "Total Return"):
            assert new[index][column] == old[index][column]
    assert set(checks["splice_checks"]) == {"1991-01-03", "2006-02-07"}
    assert new[5]["Close"] == "330"
    assert new[5]["Adj Close"] == "992.7"
    again, _ = builder.replace_gsci_prefix(new, daily, calendar)
    assert again == new


def test_full_builder_uses_raw_overlaps_independently():
    _, daily, calendar = fixture_history()
    bcom = [{"Date": day, "Close": value} for day, value in
            [("1991-01-02", 80), ("1991-01-03", 88), ("2006-02-06", 96)]]
    irx = [{"Date": day, "Close": value} for day, value in
           [("1991-01-02", 3.65), ("1991-01-03", 7.30), ("2006-02-06", 3.65)]]
    dbc = [{"Date": "2006-02-06", "Close": 40, "Adj Close": 50},
           {"Date": "2006-02-07", "Close": 42, "Adj Close": 55}]
    rows = builder.build_normalized_rows(daily, bcom, dbc, irx, calendar)
    by_date = {row["Date"]: row for row in rows}
    assert by_date["1991-01-02"]["Close"] == "300"
    assert by_date["1991-01-02"]["Adj Close"] == "900"
    assert by_date["1991-01-03"]["Close"] == "330"
    assert by_date["1991-01-03"]["Adj Close"] == "990.198"
    assert by_date["2006-02-07"]["Price Return"] == "0.05"
    assert by_date["2006-02-07"]["Total Return"] == "0.1"
    with pytest.raises(ValueError, match="BCOM must cover"):
        builder.build_normalized_rows(daily, bcom[1:], dbc, irx, calendar)
    with pytest.raises(ValueError, match="DBC must cover"):
        builder.build_normalized_rows(daily, bcom, dbc[1:], irx, calendar)


@pytest.mark.parametrize("invalid", ["NaN", "Infinity", "0", "-1"])
def test_invalid_daily_values_are_rejected(invalid):
    _, daily, calendar = fixture_history()
    daily[-1]["GSCI_ER"] = invalid
    with pytest.raises(ValueError, match="finite and positive"):
        builder.gsci_rows(daily, calendar)


def test_missing_and_duplicate_dates_fail_instead_of_filling():
    _, daily, calendar = fixture_history()
    with pytest.raises(ValueError, match="missing selected dates"):
        builder.gsci_rows(daily[:-1], calendar)
    with pytest.raises(ValueError, match="ordered and unique"):
        builder.gsci_rows(daily + [daily[-1]], calendar)


def test_tiny_rounded_negative_tr_minus_er_is_not_rejected():
    _, daily, calendar = fixture_history()
    daily[1]["GSCI_ER"] = Decimal("110.001")
    daily[1]["GSCI_TR"] = Decimal("110")
    rows = builder.gsci_rows(daily, calendar)
    builder.validate_rows(rows)
    assert Decimal(rows[1]["Total Return"]) < Decimal(rows[1]["Price Return"])


def test_changed_source_snapshot_is_rejected(tmp_path: Path):
    path = tmp_path / "changed.xlsx"
    path.write_bytes(b"unreviewed source")
    with pytest.raises(ValueError, match="reviewed snapshot"):
        gsci_daily.load_snapshot(path)


def test_staging_failure_preserves_existing_outputs(tmp_path: Path, monkeypatch):
    old, daily, calendar = fixture_history()
    new, _ = builder.replace_gsci_prefix(old, daily, calendar)
    csv_path = tmp_path / "data/processed/broad_commodities.csv"
    builder.write_csv(csv_path, old)
    parquet = csv_path.with_suffix(".parquet")
    parquet.write_bytes(b"old parquet")
    original = csv_path.read_bytes()

    def unavailable_parquet(*args, **kwargs):
        raise RuntimeError("Parquet failure")

    monkeypatch.setattr(pd.DataFrame, "to_parquet", unavailable_parquet)
    with pytest.raises(RuntimeError, match="Parquet failure"):
        builder.write_outputs(tmp_path, new, {})
    assert csv_path.read_bytes() == original
    assert parquet.read_bytes() == b"old parquet"
    assert not list(csv_path.parent.glob("*.tmp"))


@pytest.mark.parametrize("failed_name", ["broad_commodities.parquet", "broad_commodities_build.json"])
def test_final_replacement_failure_rolls_back_all_outputs(tmp_path: Path, monkeypatch, failed_name):
    old, daily, calendar = fixture_history()
    new, _ = builder.replace_gsci_prefix(old, daily, calendar)
    csv_path = tmp_path / "data/processed/broad_commodities.csv"
    metadata_path = tmp_path / "sources/manifests/broad_commodities_build.json"
    builder.write_csv(csv_path, old)
    parquet = csv_path.with_suffix(".parquet")
    parquet.write_bytes(b"old parquet")
    metadata_path.parent.mkdir(parents=True)
    metadata_path.write_bytes(b"old metadata")
    originals = {path: path.read_bytes() for path in (csv_path, parquet, metadata_path)}
    replace = Path.replace

    def injected_failure(path, target):
        if Path(target).name == failed_name and not path.name.endswith(".rollback.tmp"):
            raise OSError("Simulated final replacement failure")
        return replace(path, target)

    monkeypatch.setattr(Path, "replace", injected_failure)
    with pytest.raises(OSError, match="final replacement failure"):
        builder.write_outputs(tmp_path, new, {})
    assert {path: path.read_bytes() for path in originals} == originals
    assert not list(tmp_path.rglob("*.tmp"))


def test_newer_baseline_between_read_and_archive_is_never_overwritten(tmp_path: Path, monkeypatch):
    old, daily, calendar = fixture_history()
    csv_path = tmp_path / "data/processed/broad_commodities.csv"
    metadata_path = tmp_path / "sources/manifests/broad_commodities_build.json"
    builder.write_csv(csv_path, old)
    original_sha = builder.checksum(csv_path)
    metadata_path.parent.mkdir(parents=True)
    metadata_path.write_text(json.dumps({"csv_sha256": original_sha}), encoding="utf-8")
    newer = deepcopy(old)
    appended = newer[-1].copy()
    appended.update({"Date": "2006-02-09", "Price Return": "0", "Total Return": "0"})
    newer.append(appended)

    def newer_committed_version(root, path, expected_sha256):
        assert expected_sha256 == original_sha
        builder.write_csv(path, newer)
        return {"csv_sha256": builder.checksum(path)}

    monkeypatch.setattr(builder, "versioned_baseline", newer_committed_version)
    with pytest.raises(RuntimeError, match="does not match the migration input snapshot"):
        builder.migrate(tmp_path, daily, {"sha256": gsci_daily.SHA256}, calendar)
    assert builder.read_csv(csv_path) == newer


def test_incomplete_rollback_retains_recovery_copies(tmp_path: Path, monkeypatch):
    old, daily, calendar = fixture_history()
    new, _ = builder.replace_gsci_prefix(old, daily, calendar)
    csv_path = tmp_path / "data/processed/broad_commodities.csv"
    metadata_path = tmp_path / "sources/manifests/broad_commodities_build.json"
    builder.write_csv(csv_path, old)
    parquet = csv_path.with_suffix(".parquet")
    parquet.write_bytes(b"old parquet")
    metadata_path.parent.mkdir(parents=True)
    metadata_path.write_bytes(b"old metadata")
    replace = Path.replace

    def commit_and_rollback_failures(path, target):
        if Path(target) == metadata_path or path.name == "broad_commodities.parquet.rollback.tmp":
            raise OSError("Simulated locked file")
        return replace(path, target)

    monkeypatch.setattr(Path, "replace", commit_and_rollback_failures)
    with pytest.raises(RuntimeError, match="Recovery copies retained"):
        builder.write_outputs(tmp_path, new, {})
    assert builder.read_csv(csv_path) == old
    backup = parquet.with_suffix(".parquet.rollback.tmp")
    assert backup.read_bytes() == b"old parquet"
    assert metadata_path.read_bytes() == b"old metadata"


def test_incremental_dbc_update_preserves_imported_gsci_and_provenance(tmp_path: Path, monkeypatch):
    root = Path(__file__).resolve().parents[2]
    source_csv = root / "data/processed/broad_commodities.csv"
    source_metadata = root / "sources/manifests/broad_commodities_build.json"
    existing = builder.read_csv(source_csv)
    metadata = json.loads(source_metadata.read_text(encoding="utf-8"))
    csv_path = tmp_path / "data/processed/broad_commodities.csv"
    metadata_path = tmp_path / "sources/manifests/broad_commodities_build.json"
    builder.write_csv(csv_path, existing)
    metadata_path.parent.mkdir(parents=True)
    metadata_path.write_text(json.dumps(metadata), encoding="utf-8")
    end = date.fromisoformat(existing[-1]["Date"]) + timedelta(days=1)
    while end.weekday() >= 5:
        end += timedelta(days=1)
    quotes = {row["Date"]: {"close": float(row["Close"]), "adj": float(row["Adj Close"])}
              for row in existing[-40:]}
    quotes[end.isoformat()] = {"close": float(existing[-1]["Close"]) * 1.01,
                              "adj": float(existing[-1]["Adj Close"]) * 1.02}
    monkeypatch.setattr(incremental_update, "source_window",
                        lambda *args: ({"DBC": quotes}, {"DBC": {"sha256": "fixture"}}))
    assert incremental_update.update_asset("broad_commodities", tmp_path, end, session=object())
    updated = builder.read_csv(csv_path)
    assert [row for row in updated if row["Date"] <= "1991-01-02"] == [
        row for row in existing if row["Date"] <= "1991-01-02"]
    assert updated[-1]["Date"] == end.isoformat()
    new_metadata = json.loads(metadata_path.read_text(encoding="utf-8"))
    assert new_metadata["raw_sources"]["GSCI_ER_TR"] == metadata["raw_sources"]["GSCI_ER_TR"]
    if "gsci_migration" in metadata:
        assert new_metadata["gsci_migration"] == metadata["gsci_migration"]
    assert new_metadata["segment_row_counts"][builder.GSCI_FLAG] == 5255
    assert new_metadata["segment_row_counts"][builder.DBC_FLAG] == metadata["segment_row_counts"][builder.DBC_FLAG] + 1
    assert new_metadata["csv_sha256"] == builder.checksum(csv_path)
    assert new_metadata["parquet_sha256"] == builder.checksum(csv_path.with_suffix(".parquet"))
    assert pd.read_csv(csv_path, parse_dates=["Date"]).equals(pd.read_parquet(csv_path.with_suffix(".parquet")))
