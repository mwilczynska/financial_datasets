"""Portfolio cash accounting: entitlement, payment and fixed ex-date weights."""

from decimal import Decimal as D

import pytest

from src.distribution_assets import build_one
from src.distribution_models import ASSETS


def history(alias, dates, returns):
    flag = {"STT": "observed_yahoo_shy_1_3_treasury_total_return",
            "GLSTBOND": "observed_shy_ishg_bwz_gdp_weighted_short_govt_bond_unhedged_net_of_fee"}[alias]
    return [{"Date": on, "Total Return": value, "Quality Flag": flag} for on, value in zip(dates, returns)]


def parameters(funds):
    return {"version": "test:v1", "fund_models": {fund: {"seasonality": {"payment_lag_days": 5}} for fund in funds}}


def test_distribution_is_within_total_return_and_payment_only_moves_receivable():
    spec = next(spec for spec in ASSETS if spec.alias == "STT")
    dates = ["2025-01-02", "2025-01-03", "2025-01-08"]
    rows = history("STT", dates, ["", "0.08", "0"])
    quotes = {("SHY", on): {"Vendor Total Return": value or "0", "Distribution Return": "0.03" if i == 1 else "0",
                             "Cash Status": "observed_issuer"} for i, (on, value) in enumerate(zip(dates, ["", "0.08", "0"]))}
    source_events = {("SHY", dates[1]): {"Pay Date": dates[2]}}
    daily, events, _ = build_one(spec, rows, quotes, source_events, {"SHY": dates[0]}, {"SHY": {}}, {},
                                parameters(spec.funds), {})
    assert D(daily[1]["Unit Price USD"]) == 105
    assert D(daily[1]["Cash Entitlement USD Per Unit"]) == 3
    assert D(daily[1]["Cash Receivable USD Per Unit"]) == 3
    assert D(daily[1]["Unit Price USD"]) + D(daily[1]["Cash Receivable USD Per Unit"]) == 108
    assert D(daily[2]["Verified Cash Paid USD Per Unit"]) == 3
    assert D(daily[2]["Cash Receivable USD Per Unit"]) == 0
    assert D(events[0]["Cash USD Per Unit"]) == 3


def test_blend_payment_retains_weights_fixed_when_entitlement_was_earned():
    spec = next(spec for spec in ASSETS if spec.alias == "GLSTBOND")
    dates = ["2024-12-30", "2024-12-31", "2025-01-02"]
    rows = history("GLSTBOND", dates, ["", "0.02", "0"])
    quotes, events = {}, {}
    for fund, amount in (("SHY", "0.01"), ("ISHG", "0.02"), ("BWZ", "0.03")):
        for i, on in enumerate(dates):
            quotes[fund, on] = {"Vendor Total Return": "0.02" if i == 1 else "0",
                                "Distribution Return": amount if i == 1 else "0", "Cash Status": "observed_issuer"}
        events[fund, dates[1]] = {"Pay Date": dates[2]}
    daily, cash, _ = build_one(spec, rows, quotes, events, {fund: dates[0] for fund in spec.funds},
                               {fund: {} for fund in spec.funds}, {}, parameters(spec.funds),
                               {2024: D("0.44"), 2025: D("0.46")})
    assert D(daily[1]["Distribution Return"]) == D("0.0184")
    assert D(daily[2]["Verified Cash Paid USD Per Unit"]) == D("1.84")
    assert sum(D(row["Cash USD Per Unit"]) for row in cash) == D("1.84")


def test_missing_observed_source_is_labeled_model_fallback_not_observed_zero():
    spec = next(spec for spec in ASSETS if spec.alias == "STT")
    dates = ["2025-01-02", "2025-01-03"]
    rows = history("STT", dates, ["", "0.01"])
    quotes = {("SHY", dates[0]): {"Vendor Total Return": "0", "Distribution Return": "0", "Cash Status": "observed"}}
    model = {"SHY": {dates[1]: (D("0.005"), "modeled_test_income", "2025-01-08")}}
    daily, _, audit = build_one(spec, rows, quotes, {}, {"SHY": dates[0]}, model, {}, parameters(spec.funds), {})
    assert daily[-1]["Basis"] == "modeled"
    assert "modeled_source_cash_gap" in daily[-1]["Quality Flag"]
    assert audit["source_gap_dates"] == [dates[1]]


def test_cash_cannot_make_an_existing_total_return_path_have_negative_asset_value():
    spec = next(spec for spec in ASSETS if spec.alias == "STT")
    dates = ["2025-01-02", "2025-01-03"]
    rows = history("STT", dates, ["", "-0.99"])
    quotes = {("SHY", on): {"Vendor Total Return": "0", "Distribution Return": "0.03" if i else "0",
                             "Cash Status": "observed"} for i, on in enumerate(dates)}
    with pytest.raises(ValueError, match="nonpositive"):
        build_one(spec, rows, quotes, {("SHY", dates[1]): {"Pay Date": "2025-01-08"}},
                  {"SHY": dates[0]}, {"SHY": {}}, {}, parameters(spec.funds), {})
