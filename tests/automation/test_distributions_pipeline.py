"""Publication checks account for independent rounding without hiding bad cash."""

import pytest
from copy import deepcopy
from datetime import date, datetime, timedelta
from decimal import Decimal as D
import hashlib

from src.distribution_sources import FUNDS
from src.distributions_pipeline import validate_fund_tables
from src import distributions_pipeline as pipeline
from src.distribution_data import csv_bytes, normalized_numeric_rows
from src.distribution_models import ASSETS
from src.distribution_funds import normalize_fund
from src.distribution_sources import CashEvent, Chart
from src.distribution_validation import check_distributions


def test_native_price_and_rate_rounding_errors_add_in_publication_check():
    # TYD 2026-09-22: actual source price 21.459999084472656 and issuer cash
    # 0.24637. Both independently rounded fields are part of the output contract.
    event = {"Fund": "TYD", "Currency": "USD", "Ex Date": "2026-09-22",
             "Share Basis": "as_paid", "Cash USD Per Share": "0.24637", "Pay Date": "2026-09-29",
             "Previous Equivalent Price USD": "21.45999908", "Distribution Return": "0.011480429194"}
    prices = [{"Fund": fund} for fund in FUNDS]
    validate_fund_tables([event], prices)
    event["Distribution Return"] = "0.01148043"
    with pytest.raises(ValueError, match="TYD 2026-09-22"):
        validate_fund_tables([event], prices)


@pytest.fixture
def cash_workspace(tmp_path, monkeypatch):
    dates = []
    current = date(2020, 1, 1)
    end = date(2025, 1, 15)
    while current <= end:
        if current.weekday() < 5:
            dates.append(current.isoformat())
        current += timedelta(days=1)
    ex_dates = {on for on in dates if on[8:] == "15"}
    all_events, all_prices = [], []
    for fund in FUNDS:
        quotes, events, adjusted = {}, [], D(100)
        for on in dates:
            cash = on in ex_dates and fund not in ("GLD", "UGL")
            if cash:
                adjusted *= D("1.001")
                events.append(CashEvent(fund, on, D("0.1"), "fixture issuer", "https://example.test/facts",
                                        pay_date=(date.fromisoformat(on) + timedelta(days=4)).isoformat()))
            quotes[on] = {"close": D(100), "adj": adjusted}
        chart = Chart(fund, quotes, [], [], dates[-1])
        cash_rows, price_rows, _ = normalize_fund(chart, events, dates[-1], zero_policy=fund in ("GLD", "UGL"))
        all_events.extend(cash_rows)
        all_prices.extend(price_rows)
    all_events, all_prices = normalized_numeric_rows(all_events), normalized_numeric_rows(all_prices)
    folder = tmp_path / "data/processed"
    folder.mkdir(parents=True)
    for spec in ASSETS:
        rows = []
        for index, on in enumerate(dates):
            contribution = "0.001" if on in ex_dates and spec.family != "gold" else "0"
            flag = ("observed_price_index_sp500_total_return" if spec.alias == "USLCAP" else
                    "observed_fixture_blend" if len(spec.funds) > 1 else
                    f"observed_yahoo_{spec.funds[0].lower()}_total_return")
            rows.append({"Date": on, "Close": "100", "Price Return": "0" if index else "",
                         "Total Return": contribution if index else "", "Quality Flag": flag})
        (folder / f"{spec.stem}.csv").write_bytes(csv_bytes(list(rows[0]), rows))
    calls = []
    def collect(root, requested, **kwargs):
        calls.append(kwargs)
        begin = kwargs["start"].isoformat()
        return (deepcopy([row for row in all_events if begin <= row["Ex Date"] <= requested.isoformat()]),
                deepcopy([row for row in all_prices if begin <= row["Date"] <= requested.isoformat()]),
                {"sources": {}, "funds": {fund: {"issuer_delivery": {"delivery": "available"}} for fund in FUNDS}})
    monkeypatch.setattr(pipeline, "collect_funds", collect)
    monkeypatch.setattr(pipeline, "load_weights", lambda *args, **kwargs: ({year: D("0.45") for year in range(2020, 2026)}, {}))
    return tmp_path, end, all_events, calls


def snapshot(root):
    return {name: hashlib.sha256((root / name).read_bytes()).hexdigest()
            for name in pipeline.publication_paths()}


def test_initial_incremental_repeat_and_precision_revision_are_coherent(cash_workspace):
    root, end, events, calls = cash_workspace
    original_inputs = {spec.stem: hashlib.sha256((root / f"data/processed/{spec.stem}.csv").read_bytes()).hexdigest() for spec in ASSETS}
    assert pipeline.run_build(root, end, offline=True)
    assert check_distributions(root, end)["assets"] == 13
    initial = snapshot(root)
    assert not pipeline.run_build(root, end, offline=True)
    assert snapshot(root) == initial
    assert calls[0]["full"] and not calls[1]["full"]
    # An issuer precision correction within the year-end reconciliation window
    # changes cash and its subsequent unit path, preserving canonical returns.
    event = next(row for row in events if row["Fund"] == "SHY" and row["Ex Date"] == "2024-01-15")
    event["Cash USD Per Share"] = "0.100167"
    event["Distribution Return"] = "0.00100167"
    assert pipeline.run_build(root, end, offline=True)
    revised = snapshot(root)
    assert revised != initial
    assert not pipeline.run_build(root, end, offline=True)
    assert snapshot(root) == revised
    assert original_inputs == {spec.stem: hashlib.sha256((root / f"data/processed/{spec.stem}.csv").read_bytes()).hexdigest() for spec in ASSETS}


def test_failed_candidate_does_not_replace_any_published_artifact(cash_workspace):
    root, end, events, _ = cash_workspace
    pipeline.run_build(root, end, offline=True)
    before = snapshot(root)
    event = next(row for row in events if row["Fund"] == "SHY" and row["Ex Date"] == "2024-01-15")
    event["Cash USD Per Share"] = "-0.1"
    with pytest.raises(ValueError, match="Invalid native cash"):
        pipeline.run_build(root, end, offline=True)
    assert snapshot(root) == before


def test_merge_keeps_verified_issuer_only_events_but_stops_vendor_withdrawal():
    primary = {"Fund": "TYD", "Ex Date": "2024-12-10", "Source": "issuer", "Distribution Return": "0.02"}
    events, _, audit = pipeline.merge_funds([primary], [], [], [], "2024-01-01", full=True)
    assert events == [primary]
    assert audit["cached_primary_events_retained"]
    with pytest.raises(ValueError, match="withdrew"):
        pipeline.merge_funds([{**primary, "Source": "Yahoo chart cash events"}], [], [], [], "2024-01-01", full=True)


def test_manifest_gate_detects_artifact_and_return_input_changes(cash_workspace):
    root, end, _, _ = cash_workspace
    pipeline.run_build(root, end, offline=True)
    output = root / pipeline.OUTPUT_PATH / "fund_events.csv"
    original = output.read_bytes()
    output.write_bytes(original + b"\n")
    with pytest.raises(ValueError, match="artifact hash"):
        check_distributions(root, end)
    output.write_bytes(original)
    canonical = root / "data/processed/short_term_us_treasury.csv"
    canonical.write_bytes(canonical.read_bytes() + b"\n")
    with pytest.raises(ValueError, match="return input changed"):
        check_distributions(root, end)


def test_due_history_check_advances_once_even_without_numeric_changes(cash_workspace, monkeypatch):
    root, end, _, calls = cash_workspace
    pipeline.run_build(root, end, offline=True)
    initial = snapshot(root)
    now = datetime.now(pipeline.timezone.utc) + timedelta(days=32)
    class LaterDatetime(datetime):
        @classmethod
        def now(cls, tz=None):
            return now
    monkeypatch.setattr(pipeline, "datetime", LaterDatetime)
    assert pipeline.run_build(root, end, offline=True)
    assert calls[-1]["full"]
    checked = snapshot(root)
    assert checked[pipeline.MANIFEST_PATH] != initial[pipeline.MANIFEST_PATH]
    assert not pipeline.run_build(root, end, offline=True)
    assert snapshot(root) == checked
