"""Historical payout assumptions and anomaly handling remain explicit."""

from decimal import Decimal as D

from src.distribution_assets import blend_weights, payment_model
from src.distribution_models import (ASSETS, index_contributions, index_reference,
                                     model_annual_contribution, modeled_fund_calendar)


def equity_row(on, contribution="0.0001", *, matched=True):
    return {"Date": on, "Price Return": "0", "Total Return": contribution,
            "Quality Flag": "observed_price_index_sp500_total_return" if matched
            else "observed_price_index_crsp_large_cap_total_return"}


def test_negative_and_compensating_positive_spike_are_both_replaced():
    rows = [equity_row("2019-07-02"), equity_row("2019-07-03", "-0.0057"),
            equity_row("2019-07-05", "0.0058"), equity_row("2019-07-08")]
    values, audit = index_contributions(rows, {"monthly_contribution": "0.002"})
    assert sum(value[0] for value in values.values()) == D("0.002")
    assert all(value[1] == "modeled" for value in values.values())
    assert audit["contaminated_months"] == ["2019-07"]
    assert len(audit["raw_anomalies"]) == 2


def test_different_benchmarks_never_produce_observed_dividends():
    rows = [equity_row("1975-01-02", "0.02", matched=False),
            equity_row("1975-01-03", "-0.01", matched=False)]
    values, _ = index_contributions(rows, {"monthly_contribution": "0.003"})
    assert all(value[1:] == ("modeled", "modeled_index_benchmark_mismatch") for value in values.values())
    assert sum(value[0] for value in values.values()) == D("0.003")


def test_small_negative_rounding_is_explicit_and_not_a_modeled_material_anomaly():
    values, _ = index_contributions([equity_row("2025-10-13", "-0.0000007"),
                                    equity_row("2025-10-14", "0.0001")],
                                    {"monthly_contribution": "0.002"})
    assert values["2025-10-13"] == (D(0), "inferred", "inferred_index_rounding_zero")
    assert sum(value[0] for value in values.values()) == D("0.0000993")


def test_index_calibration_does_not_read_post_cutoff_anomalies():
    rows = [equity_row(f"2024-{month:02d}-15", "0.001") for month in range(1, 13)]
    first = index_reference(rows, "2024-12-31")
    second = index_reference(rows + [equity_row("2025-01-02", "-0.02")], "2024-12-31")
    assert first == second


def test_glstbond_uses_production_year_weight_and_only_available_international_legs():
    spec = next(spec for spec in ASSETS if spec.alias == "GLSTBOND")
    weights = {2024: D("0.44"), 2025: D("0.46")}
    both = blend_weights(spec, 2025, ("SHY", "ISHG", "BWZ"), weights)
    assert both == {"SHY": D("0.46"), "ISHG": D("0.27"), "BWZ": D("0.27")}
    one = blend_weights(spec, 2025, ("SHY", "BWZ"), weights)
    assert one == {"SHY": D("0.46"), "BWZ": D("0.54")}
    assert blend_weights(spec, 2027, ("SHY", "BWZ"), weights) == one


def test_leveraged_payout_model_uses_own_fund_parameters():
    params = {"fund_models": {"UPRO": {"intercept": "0.001", "slope": "0.2",
                                       "feature": "STT", "feature_min": "0", "feature_max": "0.06"}}}
    amount, flag = model_annual_contribution("UPRO", 1981, params,
                                            {"STT": {1981: D("0.12")}}, {1981: D("0.04")})
    assert amount == D("0.025")
    assert amount != 3 * D("0.04")
    assert flag.endswith("extrapolated")


def test_treasury_model_preserves_existing_income_contribution():
    params = {"fund_models": {"IEF": {}}}
    amount, flag = model_annual_contribution("IEF", 1980, params,
                                            {"ITT": {1980: D("0.10")}}, {})
    assert amount == D("0.10")
    assert flag == "modeled_treasury_income_calendar"


def test_partial_month_does_not_receive_a_future_scheduled_payout():
    params = {"fund_models": {"UPRO": {"intercept": "0.04", "slope": "0", "feature": "STT",
                                       "feature_min": "0", "feature_max": "1", "seasonality": {
                                           "month_weights": {"3": "0.25"}, "ex_days": {"3": [20]},
                                           "payment_lag_days": 7}}}}
    rows = [{"Date": "1980-03-03", "Total Return": ""}, {"Date": "1980-03-10", "Total Return": "0"}]
    assert modeled_fund_calendar("UPRO", rows, params, {"STT": {1980: D("0.05")}}, {}) == {}
    assert payment_model("2026-09-22", 7) == "2026-09-29"
