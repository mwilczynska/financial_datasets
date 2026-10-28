"""Versioned, retrospective cash models for pre-fund and anomalous periods.

These are explicitly hypothetical payout histories for today's fund proxies.
They are calibrated from the same source funds, not observations of nonexistent
funds. Parameters are frozen between explicit recalibrations.
"""

from __future__ import annotations

import calendar
import hashlib
import json
from collections import defaultdict
from dataclasses import dataclass
from datetime import date, timedelta
from decimal import Decimal
from statistics import median

try:
    from .distribution_sources import FUNDS, decimal_text
except ImportError:
    from distribution_sources import FUNDS, decimal_text

D = Decimal
METHOD_VERSION = "usd_cash_v1"
INDEX_ROUNDING_TOLERANCE = D("0.000002")
INDEX_MAX_DAILY_CONTRIBUTION = D("0.0015")
INDEX_POINT_ROUNDING_ALLOWANCE = D("0.02")


@dataclass(frozen=True)
class AssetSpec:
    alias: str
    stem: str
    funds: tuple[str, ...]
    family: str


ASSETS = (
    AssetSpec("USLCAP", "us_large_cap_sp500", (), "index_equity"),
    AssetSpec("STT", "short_term_us_treasury", ("SHY",), "treasury"),
    AssetSpec("ITT", "intermediate_term_us_treasury", ("IEF",), "treasury"),
    AssetSpec("LTT", "long_term_us_treasury", ("TLT",), "treasury"),
    AssetSpec("GLSTOCK", "global_stocks", ("VT",), "global_equity"),
    AssetSpec("GLBOND", "global_bonds", ("BND", "BWX"), "global_bond"),
    AssetSpec("GLSTBOND", "global_short_term_bonds", ("SHY", "ISHG", "BWZ"), "global_short_bond"),
    AssetSpec("USLCAP3X", "us_large_cap_3x_sp500", ("UPRO",), "leveraged"),
    AssetSpec("ITT3X", "intermediate_term_us_treasury_3x", ("TYD",), "leveraged"),
    AssetSpec("LTT3X", "long_term_us_treasury_3x", ("TMF",), "leveraged"),
    AssetSpec("GOLDPM", "gold", ("GLD",), "gold"),
    AssetSpec("GOLD2X", "gold_2x", ("UGL",), "gold"),
    AssetSpec("CMDTY", "broad_commodities", ("DBC",), "commodity"),
)


def index_diagnostics(rows: list[dict[str, str]]) -> tuple[set[str], dict[str, D], list[dict]]:
    """Mask whole contaminated months, including neighboring spike dates.

    Replacing an isolated negative with zero would keep its compensating positive
    spike and inflate cash. Entire contaminated months use a disclosed model.
    """
    bad_months, raw, anomalies = set(), {}, []
    for index, row in enumerate(rows):
        if "sp500_total_return" not in row["Quality Flag"] or not row["Total Return"]:
            continue
        contribution = D(row["Total Return"]) - D(row["Price Return"])
        raw[row["Date"]] = contribution
        rounding_bound = max(INDEX_ROUNDING_TOLERANCE,
                             INDEX_POINT_ROUNDING_ALLOWANCE / D(row["Close"]) if row.get("Close") else D(0))
        if contribution < -rounding_bound or contribution > INDEX_MAX_DAILY_CONTRIBUTION:
            anomalies.append({"date": row["Date"], "raw_contribution": decimal_text(contribution)})
            for neighbor in rows[max(0, index - 1):index + 2]:
                bad_months.add(neighbor["Date"][:7])
    return bad_months, raw, anomalies


def index_reference(rows: list[dict[str, str]], cutoff: str) -> dict:
    scoped = [row for row in rows if row["Date"] <= cutoff]
    bad, raw, anomalies = index_diagnostics(scoped)
    incomplete = {row["Date"][:7] for row in scoped if row["Date"] not in raw}
    monthly = defaultdict(lambda: D(0))
    for on, value in raw.items():
        if on[:7] not in bad and on[:7] not in incomplete:
            monthly[on[:7]] += value
    first = sorted(monthly)[:36]
    if len(first) < 12:
        raise ValueError("Too few validated matching-index months to calibrate USLCAP")
    reference = median(monthly[key] for key in first)
    return {"monthly_contribution": decimal_text(reference), "reference_months": first,
            "rounding_tolerance": decimal_text(INDEX_ROUNDING_TOLERANCE),
            "index_point_rounding_allowance": decimal_text(INDEX_POINT_ROUNDING_ALLOWANCE),
            "max_daily_contribution": decimal_text(INDEX_MAX_DAILY_CONTRIBUTION),
            "anomaly_count_at_calibration": len(anomalies),
            "method": "First 36 uncontaminated matching-index months; median monthly contribution.",
            "hindsight_backfill": True}


def index_contributions(rows: list[dict[str, str]], reference: dict) -> tuple[dict, dict]:
    bad, raw, anomalies = index_diagnostics(rows)
    months = defaultdict(list)
    for row in rows:
        months[row["Date"][:7]].append(row)
    trailing = []
    result = {}
    default = D(reference["monthly_contribution"])
    for month, entries in sorted(months.items()):
        matching = all(row["Date"] in raw for row in entries)
        signed = sum((raw.get(row["Date"], D(0)) for row in entries), D(0))
        usable = matching and month not in bad and signed >= 0
        target = median(trailing[-36:]) if len(trailing) >= 12 else default
        if usable:
            positive = sum((max(raw[row["Date"]], D(0)) for row in entries), D(0))
            scale = signed / positive if positive else D(1)
            reconciled = any(raw[row["Date"]] < 0 for row in entries)
            for row in entries:
                value = raw[row["Date"]]
                if value < 0:
                    result[row["Date"]] = (D(0), "inferred", "inferred_index_rounding_zero")
                else:
                    result[row["Date"]] = (value * scale, "inferred", "inferred_index_rounding_reconciled"
                                           if reconciled else "inferred_matching_index_dividend")
            trailing.append(signed)
        else:
            reason = "modeled_index_anomaly_month" if matching else "modeled_index_benchmark_mismatch"
            for row in entries:
                result[row["Date"]] = (target / len(entries) if row["Total Return"] else D(0), "modeled", reason)
    return result, {"contaminated_months": sorted(bad), "raw_anomalies": anomalies,
                    "rounding_rule": "max(2e-6, 0.02/price-index level), an explicit conservative measurement allowance.",
                    "method": "Small rounding negatives redistributed within a month preserving its signed contribution; whole-month modeled fallback for material anomalies."}


def annual_income_features(histories: dict[str, list[dict[str, str]]], fund_prices: list[dict[str, str]]) -> dict[str, dict[int, D]]:
    """Income-contribution state variables, not claimed fund distribution yields."""
    result = {}
    by_fund = defaultdict(list)
    for row in fund_prices:
        by_fund[row["Fund"]].append(row)
    for alias, fund in (("STT", "SHY"), ("ITT", "IEF"), ("LTT", "TLT")):
        annual = defaultdict(lambda: D(0))
        observed_start = min(row["Date"] for row in by_fund[fund])
        for row in histories[alias]:
            if row["Total Return"] and row["Date"] < observed_start:
                annual[int(row["Date"][:4])] += D(row["Total Return"]) - D(row["Price Return"])
        for row in by_fund[fund]:
            if row["Distribution Return"]:
                annual[int(row["Date"][:4])] += D(row["Distribution Return"])
        if any(value < 0 for value in annual.values()):
            raise ValueError(f"{alias}: negative annual income state requires investigation")
        result[alias] = dict(annual)
    collateral = defaultdict(lambda: D(0))
    for row in histories["CMDTY"]:
        if row["Total Return"] and "dbc" not in row["Quality Flag"]:
            collateral[int(row["Date"][:4])] += D(row["Total Return"]) - D(row["Price Return"])
    result["COLLATERAL"] = dict(collateral)
    return result


def _seasonality(events: list[dict[str, str]], years: set[int]) -> dict:
    values, days, per_year = defaultdict(lambda: D(0)), defaultdict(list), defaultdict(int)
    lags = []
    for event in events:
        on = event["Ex Date"]
        if int(on[:4]) not in years or not event["Distribution Return"]:
            continue
        month = int(on[5:7])
        values[month] += D(event["Distribution Return"])
        days[month].append(int(on[8:10]))
        per_year[int(on[:4]), month] += 1
        if event["Pay Date"]:
            lags.append((date.fromisoformat(event["Pay Date"]) - date.fromisoformat(on)).days)
    total = sum(values.values(), D(0))
    if not total:
        return {"month_weights": {}, "ex_days": {}, "payment_lag_days": 7,
                "lag_basis": "assumed_no_observed_payments"}
    ex_days = {}
    for month, observations in days.items():
        typical_count = max(1, round(float(median(per_year[year, month] for year in years))))
        sorted_days = sorted(observations)
        if typical_count >= 2 and len(sorted_days) >= 2:
            middle = len(sorted_days) // 2
            selected = [round(float(median(sorted_days[:middle]))), round(float(median(sorted_days[middle:])))]
        else:
            selected = [round(float(median(sorted_days)))]
        ex_days[str(month)] = sorted(set(selected))
    return {"month_weights": {str(month): decimal_text(value / total) for month, value in sorted(values.items())},
            "ex_days": ex_days, "payment_lag_days": round(float(median(lags))) if lags else 7,
            "lag_basis": "median_observed_issuer_lag" if lags else "assumed_no_verified_payment_dates"}


def _linear_fit(pairs: list[tuple[D, D]]) -> dict:
    if len(pairs) < 3:
        raise ValueError("Insufficient complete fund years for a payout model")
    xmean = sum(x for x, _ in pairs) / len(pairs)
    ymean = sum(y for _, y in pairs) / len(pairs)
    variance = sum((x - xmean) ** 2 for x, _ in pairs)
    slope = sum((x - xmean) * (y - ymean) for x, y in pairs) / variance if variance else D(0)
    if slope < 0:
        # An unstable negative income-state relationship is not extrapolated to
        # the high-rate 1970s. Use a disclosed constant median instead.
        slope, intercept, method = D(0), median(y for _, y in pairs), "median_after_negative_slope"
    else:
        intercept, method = ymean - slope * xmean, "nonnegative_cash_linear_income_state"
    residuals = [y - max(D(0), intercept + slope * x) for x, y in pairs]
    return {"intercept": decimal_text(intercept), "slope": decimal_text(slope), "method": method,
            "feature_min": decimal_text(min(x for x, _ in pairs)),
            "feature_max": decimal_text(max(x for x, _ in pairs)),
            "response_min": decimal_text(min(y for _, y in pairs)),
            "response_max": decimal_text(max(y for _, y in pairs)),
            "median": decimal_text(median(y for _, y in pairs)),
            "mean_absolute_residual": decimal_text(sum(abs(value) for value in residuals) / len(residuals))}


def calibrate(histories: dict, fund_events: list[dict[str, str]], fund_prices: list[dict[str, str]],
              cutoff: str) -> tuple[dict, list[dict[str, str]]]:
    index_ref = index_reference(histories["USLCAP"], cutoff)
    index_map, _ = index_contributions([row for row in histories["USLCAP"] if row["Date"] <= cutoff], index_ref)
    index_annual = defaultdict(lambda: D(0))
    for on, (value, _, _) in index_map.items():
        index_annual[int(on[:4])] += value
    features = annual_income_features(histories, fund_prices)
    events_by_fund, prices_by_fund = defaultdict(list), defaultdict(list)
    for row in fund_events:
        events_by_fund[row["Fund"]].append(row)
    for row in fund_prices:
        prices_by_fund[row["Fund"]].append(row)
    models, summaries = {}, []
    for fund in FUNDS:
        prices = prices_by_fund[fund]
        first_year = int(min(row["Date"] for row in prices)[:4])
        years = set(range(first_year + 1, int(cutoff[:4]) + 1))
        contributions = defaultdict(lambda: D(0))
        counts = defaultdict(int)
        for row in prices:
            if row["Date"] <= cutoff and row["Distribution Return"]:
                contributions[int(row["Date"][:4])] += D(row["Distribution Return"])
        for event in events_by_fund[fund]:
            counts[int(event["Ex Date"][:4])] += 1
        feature = "ITT" if fund in ("BND", "BWX") else "STT"
        pairs = [(features[feature][year], contributions[year]) for year in sorted(years) if year in features[feature]]
        if fund in ("GLD", "UGL"):
            model = {"method": "zero_routine_cash_policy", "intercept": "0", "slope": "0",
                     "median": "0", "feature_min": "0", "feature_max": "0"}
        else:
            model = _linear_fit(pairs)
        models[fund] = {**model, "feature": feature, "calibration_years": sorted(years),
                        "seasonality": _seasonality(events_by_fund[fund], years),
                        "hindsight_backfill": True,
                        "response_definition": "Sum of daily cash/preceding-price contributions; not buy-and-hold cash yield."}
        if fund == "VT":
            ratios = [contributions[year] / index_annual[year] for year in sorted(years) if index_annual[year] > 0]
            models[fund]["index_income_ratio"] = decimal_text(median(ratios))
        for year in sorted(years):
            summaries.append({"Fund": fund, "Year": str(year),
                              "Distribution Contribution Sum": decimal_text(contributions[year]),
                              "Cash Event Count": str(counts[year]),
                              "Income Feature": feature,
                              "Income Feature Value": decimal_text(features[feature].get(year)),
                              "Calibration Cutoff": cutoff})
    params = {"method_version": METHOD_VERSION, "calibration_cutoff": cutoff,
              "index_reference": index_ref, "fund_models": models,
              "scope": "Retrospective hypothetical payout backfills; not point-in-time forecasts or observed pre-fund history."}
    digest = hashlib.sha256(json.dumps(params, sort_keys=True).encode()).hexdigest()[:12]
    params["version"] = f"{METHOD_VERSION}:{digest}"
    return params, summaries


def model_annual_contribution(fund: str, year: int, params: dict, features: dict,
                              index_annual: dict[int, D]) -> tuple[D, str]:
    model = params["fund_models"][fund]
    if fund in ("GLD", "UGL"):
        return D(0), "modeled_zero_routine_cash_policy"
    if fund in ("SHY", "IEF", "TLT"):
        alias = {"SHY": "STT", "IEF": "ITT", "TLT": "LTT"}[fund]
        return features[alias][year], "modeled_treasury_income_calendar"
    if fund == "VT":
        return index_annual[year] * D(model["index_income_ratio"]), "modeled_vt_scaled_index_income"
    value = features[model["feature"]][year]
    if fund == "DBC" and year in features["COLLATERAL"]:
        value = features["COLLATERAL"][year]
    estimate = max(D(0), D(model["intercept"]) + D(model["slope"]) * value)
    status = "modeled_current_fund_income_state"
    if value < D(model["feature_min"]) or value > D(model["feature_max"]):
        status += "_extrapolated"
    return estimate, status


def modeled_fund_calendar(fund: str, rows: list[dict[str, str]], params: dict,
                          features: dict, index_annual: dict[int, D]) -> dict[str, tuple[D, str, str]]:
    months = defaultdict(list)
    for row in rows:
        months[row["Date"][:7]].append(row["Date"])
    model = params["fund_models"][fund]
    seasonality = model["seasonality"]
    result = {}
    for month, dates in months.items():
        year, month_number = map(int, month.split("-"))
        annual, status = model_annual_contribution(fund, year, params, features, index_annual)
        weight = D(seasonality["month_weights"].get(str(month_number), "0"))
        targets = seasonality["ex_days"].get(str(month_number), [])
        if not annual or not weight or not targets:
            continue
        selected = []
        for desired in targets:
            selected.append(min(dates, key=lambda on: (abs(int(on[8:10]) - desired), on)))
        selected = sorted(set(selected))
        for on in selected:
            # Do not pull a not-yet-due monthly payment into a partial final month.
            desired = min(targets, key=lambda target: abs(int(on[8:10]) - target))
            if int(on[8:10]) < desired and on == dates[-1] and month == rows[-1]["Date"][:7]:
                continue
            if on == rows[0]["Date"]:
                continue
            payment = date.fromisoformat(on) + timedelta(days=seasonality["payment_lag_days"])
            while payment.weekday() >= 5:
                payment += timedelta(days=1)
            result[on] = (annual * weight / len(selected), status, payment.isoformat())
    return result
