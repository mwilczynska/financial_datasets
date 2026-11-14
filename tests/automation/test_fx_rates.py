"""ECB parsing, catch-up, idempotence and publication-gate checks for the FX datasets."""

from __future__ import annotations

import hashlib
import io
import json
import sys
import zipfile
from datetime import date, timedelta
from decimal import Decimal
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "src"))
import fx_rates as fx
import incremental_update as update

FIRST = date(2026, 8, 3)


def ecb_zip(days: int, *, bump: dict[str, str] | None = None, blank_aud: frozenset[str] = frozenset()) -> bytes:
    """A reference-rate archive in the ECB layout: newest first, trailing comma, N/A gaps."""
    lines = ["Date,USD,JPY,GBP,AUD,"]
    for index in reversed(range(days)):
        day = FIRST + timedelta(days=index)
        if day.weekday() >= 5:
            continue
        key = day.isoformat()
        usd = (bump or {}).get(key, f"{1.1 + index / 1000:.4f}")
        aud = "N/A" if key in blank_aud else f"{1.6 + index / 500:.4f}"
        lines.append(f"{key},{usd},170.1,{0.85 + index / 2000:.5f},{aud},")
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w") as archive:
        archive.writestr(fx.ECB_MEMBER, "\n".join(lines) + "\n")
    return buffer.getvalue()


class FakeSession:
    def __init__(self, content: bytes):
        self.content = content

    def get(self, url, **kwargs):
        assert url == fx.ECB_URL
        return self

    def raise_for_status(self):
        return None


def sample_root(tmp_path: Path, stem: str, days: int) -> Path:
    pair = fx.PAIRS[stem]
    series = fx.ecb_series(pair, fx.parse_ecb(ecb_zip(days)))
    rows = fx.make_rows([(day, value, fx.ECB_SOURCE, pair.ecb_flag, pair.ecb_notes) for day, value in series.items()])
    processed = tmp_path / "data" / "processed"
    manifests = tmp_path / "sources" / "manifests"
    manifests.mkdir(parents=True)
    update.write_rows(processed / f"{stem}.csv", rows)
    update.write_parquet(processed / f"{stem}.csv", processed / f"{stem}.parquet")
    (manifests / f"{stem}_build.json").write_text(json.dumps({"asset_id": stem}), encoding="utf-8")
    return tmp_path


def test_ecb_parse_and_crosses() -> None:
    rates = fx.parse_ecb(ecb_zip(5, blank_aud=frozenset({"2026-08-04"})))
    assert list(rates) == sorted(rates) and len(rates) == 5
    day = "2026-08-05"
    assert fx.ecb_series(fx.PAIRS["fx_eur_usd"], rates)[day] == Decimal("1.1020")
    assert fx.ecb_series(fx.PAIRS["fx_gbp_usd"], rates)[day] == Decimal("1.1020") / Decimal("0.85100")
    aud = fx.ecb_series(fx.PAIRS["fx_aud_usd"], rates)
    assert aud[day] == Decimal("1.1020") / Decimal("1.6040")
    assert "2026-08-04" not in aud  # an unpublished leg leaves no row rather than a carried rate


def test_ecb_rejects_wrong_archive() -> None:
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w") as archive:
        archive.writestr("other.csv", "Date,USD\n")
    with pytest.raises(RuntimeError, match="unexpected members"):
        fx.parse_ecb(buffer.getvalue())


@pytest.mark.parametrize("stem", sorted(fx.PAIRS))
def test_catchup_idempotence_and_gate(tmp_path: Path, stem: str) -> None:
    root = sample_root(tmp_path, stem, 40)
    path = root / "data" / "processed" / f"{stem}.csv"
    before = update.read_rows(path)
    target = date(2026, 9, 18)
    assert update.update_asset(stem, root, target, session=FakeSession(ecb_zip(60)))
    rows = update.read_rows(path)
    assert rows[: len(before)] == before
    assert rows[-1]["Date"] == "2026-09-18" and len(rows) == len(before) + 5
    assert all(row["Quality Flag"] == fx.PAIRS[stem].ecb_flag for row in rows)
    fx.check_recent(root, stem, rows, target, {row["Date"] for row in rows[len(before):]})
    first_hash = hashlib.sha256(path.read_bytes()).hexdigest()
    assert not update.update_asset(stem, root, target, session=FakeSession(ecb_zip(60)))
    assert hashlib.sha256(path.read_bytes()).hexdigest() == first_hash
    metadata = json.loads((root / "sources/manifests" / f"{stem}_build.json").read_text(encoding="utf-8"))
    assert metadata["last_date"] == "2026-09-18" and metadata["row_count"] == len(rows)
    assert metadata["incremental_update"]["recent_sources"]["ECB_EUROFXREF"]["url"] == fx.ECB_URL


def test_gate_rejects_tampered_tail_and_stale_source(tmp_path: Path) -> None:
    stem = "fx_eur_usd"
    root = sample_root(tmp_path, stem, 40)
    target = date(2026, 9, 18)
    update.update_asset(stem, root, target, session=FakeSession(ecb_zip(60)))
    rows = update.read_rows(root / "data" / "processed" / f"{stem}.csv")
    tampered = [dict(row) for row in rows]
    tampered[-1]["Close"] = tampered[-1]["Adj Close"] = "1.2"
    with pytest.raises(RuntimeError, match="disagrees with the ECB"):
        fx.check_recent(root, stem, tampered, target, set())
    with pytest.raises(RuntimeError, match="differs from latest ECB date"):
        fx.check_recent(root, stem, rows[:-1], target, set())
    with pytest.raises(RuntimeError, match="stale"):
        fx.check_recent(root, stem, rows, target + timedelta(days=30), set())
    fx.recent_path(root, stem).unlink()
    with pytest.raises(RuntimeError, match="missing current ECB"):
        fx.check_recent(root, stem, rows, target, set())


def test_update_fails_closed_without_touching_outputs(tmp_path: Path) -> None:
    stem = "fx_eur_usd"
    root = sample_root(tmp_path, stem, 40)
    path = root / "data" / "processed" / f"{stem}.csv"
    original = path.read_bytes()
    existing = update.read_rows(path)
    last = date.fromisoformat(existing[-1]["Date"])
    anchor = [row["Date"] for row in existing if row["Date"] < (last - timedelta(days=14)).isoformat()][-1]
    with pytest.raises(RuntimeError, match="disagrees with the committed overlap anchor"):
        update.update_asset(stem, root, date(2026, 9, 18), session=FakeSession(ecb_zip(60, bump={anchor: "1.5000"})))
    with pytest.raises(RuntimeError, match="would delete committed dates"):
        update.update_asset(stem, root, date(2026, 9, 18), session=FakeSession(ecb_zip(38)))
    with pytest.raises(RuntimeError, match="stale"):
        update.update_asset(stem, root, date(2026, 10, 30), session=FakeSession(ecb_zip(60)))
    assert path.read_bytes() == original
    assert not fx.recent_path(root, stem).exists()


def test_recent_revision_inside_overlap_is_applied(tmp_path: Path) -> None:
    stem = "fx_eur_usd"
    root = sample_root(tmp_path, stem, 40)
    path = root / "data" / "processed" / f"{stem}.csv"
    before = update.read_rows(path)
    revised_day = before[-2]["Date"]
    assert update.update_asset(stem, root, date(2026, 9, 11),
                               session=FakeSession(ecb_zip(40, bump={revised_day: "1.2500"})))
    after = {row["Date"]: row for row in update.read_rows(path)}
    assert after[revised_day]["Close"] == "1.25"
    assert all(after[row["Date"]] == row for row in before[:-2])


def test_historical_levels_model_1970_aud_and_check_the_splice() -> None:
    pair = fx.PAIRS["fx_aud_usd"]
    weekdays = [date(1970, 1, 1) + timedelta(days=i) for i in range(11000)]
    weekdays = [day for day in weekdays if day.weekday() < 5]
    gbp = {day.isoformat(): Decimal("0.42") for day in weekdays if day >= fx.START_DATE}
    aud = {day: value * Decimal("2.15") for day, value in gbp.items() if day >= "1971-01-04"}
    ecb = {day: 1 / value for day, value in aud.items() if day >= "1999-01-04"}
    levels, details = fx.historical_levels(pair, aud, ecb, gbp)
    assert levels[0][0] == "1970-01-02" and levels[0][3] == fx.PEG_FLAG
    assert details["sterling_peg"]["aud_per_gbp_ratio"] == "2.15"
    assert {level[3] for level in levels} == {fx.PEG_FLAG, pair.bis_flag, pair.ecb_flag}
    assert all(abs(level[1] - 1 / (Decimal("0.42") * Decimal("2.15"))) < Decimal("1e-20") for level in levels)
    wrong = {day: value * Decimal("1.01") for day, value in ecb.items()}
    with pytest.raises(RuntimeError, match="disagree on the 1999 overlap"):
        fx.historical_levels(pair, aud, wrong, gbp)
    with pytest.raises(RuntimeError, match="no peg model"):
        fx.historical_levels(pair, aud, ecb)
