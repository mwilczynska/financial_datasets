"""Focused fixtures for catch-up, repeat runs, CPI publication, and source failure."""

from __future__ import annotations

import hashlib
import json
import sys
from datetime import date, timedelta
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "src"))
import build_cpi_inflation as cpi
import incremental_update as update


def sample_root(tmp_path: Path) -> tuple[Path, dict[str, dict[str, float]]]:
    stem = "broad_commodities"
    processed = tmp_path / "data" / "processed"
    manifests = tmp_path / "sources" / "manifests"
    processed.mkdir(parents=True)
    manifests.mkdir(parents=True)
    first = date(2026, 8, 1)
    quotes = {}
    rows = []
    for index in range(40):
        day = (first + timedelta(days=index)).isoformat()
        quotes[day] = {"close": 50 + index, "adj": 60 + index}
        if index >= 25:
            continue
        price = "" if index == 0 else update.round_number(update.ratio(50 + index, 49 + index))
        total = "" if index == 0 else update.round_number(update.ratio(60 + index, 59 + index))
        rows.append({"Date": day, "Open": "", "High": "", "Low": "", "Close": update.round_number(100 * (50 + index) / 50),
                     "Adj Close": update.round_number(100 * (60 + index) / 60), "Volume": "", "Price Return": price,
                     "Total Return": total, "Source": "Yahoo DBC", "Quality Flag": update.ASSETS[stem].expected_flag,
                     "Source Notes": "Observed ETF"})
    path = processed / f"{stem}.csv"
    update.write_rows(path, rows)
    update.write_parquet(path, processed / f"{stem}.parquet")
    (manifests / f"{stem}_build.json").write_text(json.dumps({"asset_id": stem, "row_count": len(rows)}), encoding="utf-8")
    return tmp_path, quotes


def test_catchup_and_idempotence(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    root, quotes = sample_root(tmp_path)
    monkeypatch.setattr(update, "source_window", lambda *args: ({"DBC": quotes}, {"DBC": {"sha256": "fixture"}}))
    path = root / "data" / "processed" / "broad_commodities.csv"
    target = date(2026, 8, 30)
    assert update.update_asset("broad_commodities", root, target, session=object())
    rows = update.read_rows(path)
    assert rows[-1]["Date"] == target.isoformat()
    assert len(rows) == 30
    first_hash = hashlib.sha256(path.read_bytes()).hexdigest()
    assert not update.update_asset("broad_commodities", root, target, session=object())
    assert hashlib.sha256(path.read_bytes()).hexdigest() == first_hash
    assert update.update_asset("broad_commodities", root, date(2026, 9, 4), session=object())
    assert len(update.read_rows(path)) == 35


def test_failed_source_leaves_outputs_untouched(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    root, _ = sample_root(tmp_path)
    path = root / "data" / "processed" / "broad_commodities.csv"
    original = path.read_bytes()
    monkeypatch.setattr(update, "source_window", lambda *args: (_ for _ in ()).throw(RuntimeError("source unavailable")))
    with pytest.raises(RuntimeError, match="source unavailable"):
        update.update_asset("broad_commodities", root, date(2026, 8, 30), session=object())
    assert path.read_bytes() == original


def test_cpi_release_revises_only_recent_carry(tmp_path: Path) -> None:
    processed = tmp_path / "data" / "processed"
    manifests = tmp_path / "sources" / "manifests"
    processed.mkdir(parents=True)
    manifests.mkdir(parents=True)
    old_monthly = [(date(2026, 5, 1), 320.0), (date(2026, 6, 1), 321.0)]
    existing = []
    previous = None
    for offset in range(75):
        day = date(2026, 5, 1) + timedelta(days=offset)
        level, flag, notes = cpi.daily_cpi_level(day, old_monthly)
        value = cpi.round_float(level)
        daily_return = "" if previous is None else cpi.round_float(level / previous - 1)
        existing.append({"Date": day.isoformat(), "Open": "", "High": "", "Low": "", "Close": value,
                         "Adj Close": value, "Volume": "", "Price Return": daily_return, "Total Return": daily_return,
                         "Source": cpi.SOURCE, "Quality Flag": flag, "Source Notes": notes})
        previous = level
    update.write_rows(processed / "cpi_inflation.csv", existing)
    (manifests / "cpi_inflation_build.json").write_text(json.dumps({"latest_monthly_observation": "2026-06-01"}), encoding="utf-8")
    payload = {"status": "REQUEST_SUCCEEDED", "Results": {"series": [{"data": [
        {"year": "2026", "period": "M07", "value": "322.2"},
        {"year": "2026", "period": "M06", "value": "321.0"},
        {"year": "2026", "period": "M05", "value": "320.0"},
    ]}]}}

    class Response:
        def raise_for_status(self) -> None: pass
        def json(self) -> dict: return payload

    class Session:
        def post(self, *args, **kwargs) -> Response: return Response()

    rows, _, monthly_date, anchor = update.build_cpi_recent(tmp_path, existing, date(2026, 7, 16), Session())
    assert monthly_date == "2026-07-01"
    assert anchor == "2026-06-01"
    assert rows[0] == existing[0]
    assert rows[-1]["Date"] == "2026-07-16"
    assert next(row for row in rows if row["Date"] == "2026-07-01")["Close"] == "322.2"
    assert next(row for row in rows if row["Date"] == "2026-06-15")["Quality Flag"] == cpi.INTERPOLATED_FLAG
