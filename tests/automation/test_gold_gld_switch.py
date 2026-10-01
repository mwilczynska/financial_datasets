"""Regression checks for the GLD splice and LBMA-independent daily publication."""
import hashlib
import json
import sys
from datetime import date, datetime, timezone
from decimal import Decimal
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "src"))
sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "scripts"))
import build_gold as gold
import build_gold_2x as leveraged
import incremental_update as update
import check_daily_diff as gate
from test_incremental_update import sample_root


def model_fixture():
    return [gold._emit("1970-01-02", 35, 35, "", "", gold.MODEL_FLAG, gold.MODEL_SOURCE, gold.MODEL_NOTES),
            gold._emit("2004-11-17", 440, 400, "", "", gold.MODEL_FLAG, gold.MODEL_SOURCE, gold.MODEL_NOTES)]


def test_stitch_uses_first_gld_quote_and_separate_price_adjusted_returns():
    price = {"2004-11-18": 44, "2004-11-19": 48.4}
    adj = {"2004-11-18": 40, "2004-11-19": 42}
    model = model_fixture()
    rows = gold.stitch_rows(model, price, adj, date(2004, 11, 19))
    assert rows[:2] == model
    assert rows[2]["Date"] == "2004-11-18"
    assert rows[2]["Close"] == "440" and rows[2]["Adj Close"] == "400"
    assert rows[2]["Price Return"] == rows[2]["Total Return"] == "0"
    assert rows[3]["Close"] == "484" and rows[3]["Adj Close"] == "420"
    assert Decimal(rows[3]["Price Return"]) == Decimal("0.1")
    assert Decimal(rows[3]["Total Return"]) == Decimal("0.05")
    assert rows[3]["Quality Flag"] == gold.ETF_FLAG


@pytest.mark.parametrize("price,adj", [
    ({"2004-11-19": 44}, {"2004-11-19": 44}),
    ({"2004-11-18": 44}, {}),
    ({"2004-11-18": float("nan")}, {"2004-11-18": 44}),
])
def test_incomplete_or_invalid_history_cannot_move_the_splice(price, adj):
    with pytest.raises(RuntimeError):
        gold.stitch_rows(model_fixture(), price, adj, date(2004, 11, 19))


def gold_root(tmp_path):
    root, quotes = sample_root(tmp_path)
    original = root / "data/processed/broad_commodities.csv"
    rows = update.read_rows(original)
    for row in rows:
        row.update({"Source": gold.ETF_SOURCE, "Quality Flag": gold.ETF_FLAG, "Source Notes": gold.ETF_NOTES})
    path = root / "data/processed/gold.csv"
    update.write_rows(path, rows)
    update.write_parquet(path, path.with_suffix(".parquet"))
    (root / "sources/manifests/gold_build.json").write_text(json.dumps({"asset_id": "gold"}), encoding="utf-8")
    return root, quotes


def test_gold_catchup_and_gate_use_only_gld_and_repeat_without_rewriting(tmp_path, monkeypatch):
    root, quotes = gold_root(tmp_path)
    monkeypatch.setattr(update, "source_window", lambda *args: ({"GLD": quotes}, {"GLD": {"sha256": "fixture"}}))

    class NoExtraRequests:
        def get(self, *args, **kwargs):
            raise AssertionError("Unexpected LBMA or other secondary request")

    target = date(2026, 8, 30)
    assert update.update_asset("gold", root, target, session=NoExtraRequests())
    rows = update.read_rows(root / "data/processed/gold.csv")
    assert rows[-1]["Date"] == target.isoformat()
    gate.check_source_tail("gold", rows, {"GLD": quotes}, root, {}, set())
    gate.check_arithmetic("gold", rows)
    gate.check_parquet(root, "gold", rows)
    before = hashlib.sha256((root / "data/processed/gold.csv").read_bytes()).hexdigest()
    assert not update.update_asset("gold", root, target, session=NoExtraRequests())
    assert hashlib.sha256((root / "data/processed/gold.csv").read_bytes()).hexdigest() == before
    rows[-1]["Price Return"] = "0.9"
    with pytest.raises(RuntimeError, match="price return disagrees"):
        gate.check_source_tail("gold", rows, {"GLD": quotes}, root, {}, set())


def test_failed_gld_source_preserves_all_gold_outputs(tmp_path, monkeypatch):
    root, _ = gold_root(tmp_path)
    paths = [root / "data/processed/gold.csv", root / "data/processed/gold.parquet",
             root / "sources/manifests/gold_build.json"]
    before = [p.read_bytes() for p in paths]
    monkeypatch.setattr(update, "source_window", lambda *args: (_ for _ in ()).throw(RuntimeError("GLD unavailable")))
    with pytest.raises(RuntimeError, match="GLD unavailable"):
        update.update_asset("gold", root, date(2026, 8, 30), session=object())
    assert [p.read_bytes() for p in paths] == before


def test_leveraged_model_requires_preserved_spot_instead_of_gld_returns(tmp_path):
    path = tmp_path / "data/processed/gold.csv"
    row = gold._emit("2004-11-18", 440, 400, "0", "0", gold.ETF_FLAG, gold.ETF_SOURCE, gold.ETF_NOTES)
    gold.write_csv(path, [row])
    with pytest.raises(RuntimeError, match="Missing preserved GOLD2X spot input"):
        leveraged.load_base_price_returns(path)


def test_full_gold_builder_uses_published_model_and_never_requests_lbma(tmp_path, monkeypatch):
    baseline = tmp_path / "data/processed/gold.csv"
    model = model_fixture()
    gold.write_csv(baseline, model)
    dates = ["2004-11-18", "2004-11-19"]
    payload = {"chart": {"result": [{"meta": {"symbol": "GLD"},
        "timestamp": [int(datetime.fromisoformat(day).replace(tzinfo=timezone.utc).timestamp()) for day in dates],
        "indicators": {"quote": [{"close": [44.0, 48.4]}], "adjclose": [{"adjclose": [40.0, 42.0]}]}}],
        "error": None}}
    monkeypatch.setattr(gold, "fetch_chart", lambda *args, **kwargs: payload)
    monkeypatch.setattr(gold, "fetch_lbma_gold_pm", lambda: (_ for _ in ()).throw(AssertionError("Unexpected LBMA request")))
    monkeypatch.setattr(sys, "argv", ["build_gold.py", "--root", str(tmp_path), "--end-date", "2004-11-19"])
    gold.main()
    rows = update.read_rows(baseline)
    assert rows[:2] == model
    assert rows[2]["Date"] == gold.ETF_FIRST_DATE
    metadata = json.loads((tmp_path / "sources/manifests/gold_build.json").read_text())
    assert metadata["csv_sha256"] == update.checksum(baseline)
    assert metadata["build_sources"]["historical_model"]["mode"] == "preserved_published_model"
    gate.check_parquet(tmp_path, "gold", rows)
