"""Cash amounts remain valid across forward/reverse splits and source conflicts."""

from decimal import Decimal as D

from src.distribution_funds import normalize_fund
from src.distribution_sources import CashEvent, Chart, Split, validate_issuer_event


def sample_chart(fund="UPRO", *, factor="2", vendor="0.5", with_event=True):
    event = CashEvent(fund, "2025-01-03", D(vendor), "Yahoo chart cash events", "vendor",
                      share_basis="split_adjusted_to_snapshot", quality="observed_vendor_rounded")
    return Chart(fund, {"2025-01-02": {"close": D(50), "adj": D("49.5")},
                        "2025-01-03": {"close": D("49.5"), "adj": D("49.5")}},
                 [event] if with_event else [], [Split("2025-02-03", D(factor))], "2025-01-03")


def test_native_amount_and_distribution_rate_have_different_unit_factors():
    chart = sample_chart()
    event = CashEvent("UPRO", "2025-01-03", D(1), "issuer", "issuer", pay_date="2025-01-08")
    events, prices, diagnostic = normalize_fund(chart, [event], "2025-01-03")
    assert events[0]["Cash USD Per Share"] == "1"
    assert events[0]["Previous Equivalent Price USD"] == "100"
    assert D(events[0]["Distribution Return"]) == D("0.01")
    assert prices[0]["Price USD As Paid"] == "100"
    assert prices[-1]["Price USD As Paid"] == "99"
    assert not diagnostic["amount_conflicts"]


def test_reverse_split_does_not_multiply_economic_cash_yield():
    chart = sample_chart(factor="0.1")
    events, _, _ = normalize_fund(chart, [], "2025-01-03")
    assert D(events[0]["Cash USD Per Share"]) == D("0.05")
    assert D(events[0]["Distribution Return"]) == D("0.01")


def test_precise_issuer_cash_overrides_rounded_vendor_and_retains_conflicts():
    chart = sample_chart(factor="1")
    event = CashEvent("UPRO", "2025-01-03", D("0.500167"), "issuer", "issuer")
    events, _, _ = normalize_fund(chart, [event], "2025-01-03")
    assert events[0]["Cash USD Per Share"] == "0.500167"
    assert events[0]["Vendor Cash USD Per Share"] == "0.5"
    assert events[0]["Reconciliation"] == "issuer_matches_vendor_rounding"
    event.amount = D("0.25")
    events, _, diagnostic = normalize_fund(chart, [event], "2025-01-03")
    assert events[0]["Cash USD Per Share"] == "0.25"
    assert events[0]["Quality Flag"] == "observed_issuer_vendor_conflict"
    assert diagnostic["amount_conflicts"][0]["vendor_usd"] == "0.5"


def test_cash_adjustment_without_an_event_stays_unknown():
    chart = sample_chart(with_event=False)
    events, prices, diagnostics = normalize_fund(chart, [], "2025-01-03")
    assert not events
    assert prices[-1]["Distribution Return"] == ""
    assert prices[-1]["Cash Status"] == "unknown_cash_adjustment_without_event"
    assert diagnostics["unknown_adjustment_dates"] == ["2025-01-03"]


def test_zero_policy_does_not_drop_an_exceptional_future_cash_event():
    chart = sample_chart(fund="GLD", factor="1")
    events, _, diagnostics = normalize_fund(chart, [], "2025-01-03", zero_policy=True)
    assert events[0]["Cash USD Per Share"] == "0.5"
    assert not diagnostics["zero_policy"]


def test_contradictory_issuer_payment_date_is_retained_as_unresolved_evidence():
    event = CashEvent("BWX", "2008-03-03", D("0.1"), "issuer", "issuer", pay_date="2008-02-11")
    validate_issuer_event(event)
    assert event.pay_date == ""
    assert event.source_pay_date == "2008-02-11"
    assert "quarantined" in event.notes
    assert event.quality == "observed_issuer_payment_date_unresolved"
