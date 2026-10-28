"""Synthetic USD-unit cash flows that preserve the published total returns."""

from __future__ import annotations

from bisect import bisect_left
from collections import defaultdict
from datetime import date, timedelta
from decimal import Decimal

try:
    from .distribution_models import (ASSETS, AssetSpec, annual_income_features, index_contributions,
                                      modeled_fund_calendar)
    from .distribution_sources import decimal_text
except ImportError:
    from distribution_models import (ASSETS, AssetSpec, annual_income_features, index_contributions,
                                     modeled_fund_calendar)
    from distribution_sources import decimal_text

D = Decimal
UNIT_DEFINITION = "One synthetic unit initially USD 100; cash is not reinvested inside the unit."
DAILY_COLUMNS = [
    "Date", "Asset", "Currency", "Unit Price USD", "Total Return", "Distribution Return",
    "Return Ex Distribution Residual", "Cash Entitlement USD Per Unit",
    "Verified Cash Paid USD Per Unit", "Modeled Cash Paid USD Per Unit", "Cash Receivable USD Per Unit",
    "Basis", "Quality Flag", "Model Version",
]
ASSET_EVENT_COLUMNS = [
    "Asset", "Ex Date", "Fund", "Distribution Return", "Cash USD Per Unit", "Pay Date",
    "Modeled Pay Date", "Payment Date Basis", "Cash Basis", "Quality Flag", "Model Version",
]


def blend_weights(spec: AssetSpec, year: int, available: tuple[str, ...], us_weights: dict[int, D]) -> dict[str, D]:
    if spec.alias == "GLBOND":
        if set(available) != {"BND", "BWX"}:
            raise ValueError("GLBOND requires both production fund legs")
        return {"BND": D("0.45"), "BWX": D("0.55")}
    if spec.alias == "GLSTBOND":
        intl = tuple(fund for fund in ("ISHG", "BWZ") if fund in available)
        if "SHY" not in available or not intl:
            raise ValueError("GLSTBOND requires SHY and at least one international return leg")
        last_year = max(key for key in us_weights if key <= year)
        weight = us_weights[last_year]
        return {"SHY": weight, **{fund: (1 - weight) / len(intl) for fund in intl}}
    return {spec.funds[0]: D(1)}


def observed_source(spec: AssetSpec, flag: str) -> bool:
    if spec.family in ("global_bond", "global_short_bond"):
        return flag.startswith("observed_")
    if not spec.funds:
        return False
    fund = spec.funds[0].lower()
    return flag.startswith("observed_") and (f"_{fund}_" in flag)


def payment_model(on: str, lag: int) -> str:
    payment = date.fromisoformat(on) + timedelta(days=lag)
    while payment.weekday() >= 5:
        payment += timedelta(days=1)
    return payment.isoformat()


def build_assets(histories: dict, fund_events: list[dict[str, str]], fund_prices: list[dict[str, str]],
                 params: dict, us_weights: dict[int, D]) -> tuple[dict[str, list], list, dict]:
    fund_daily = {(row["Fund"], row["Date"]): row for row in fund_prices}
    event_lookup = {(row["Fund"], row["Ex Date"]): row for row in fund_events}
    first_quote = {}
    for row in fund_prices:
        first_quote[row["Fund"]] = min(first_quote.get(row["Fund"], row["Date"]), row["Date"])
    features = annual_income_features(histories, fund_prices)
    index_map, index_audit = index_contributions(histories["USLCAP"], params["index_reference"])
    index_annual = defaultdict(lambda: D(0))
    for on, (value, _, _) in index_map.items():
        index_annual[int(on[:4])] += value
    outputs, cash_events, audit = {}, [], {"index": index_audit, "assets": {}}
    for spec in ASSETS:
        model_calendars = {fund: modeled_fund_calendar(fund, histories[spec.alias], params, features, index_annual)
                           for fund in spec.funds}
        rows, events, facts = build_one(spec, histories[spec.alias], fund_daily, event_lookup, first_quote,
                                       model_calendars, index_map, params, us_weights)
        outputs[spec.stem] = rows
        cash_events.extend(events)
        audit["assets"][spec.alias] = facts
    cash_events.sort(key=lambda row: (row["Asset"], row["Ex Date"], row["Fund"]))
    return outputs, cash_events, audit


def build_one(spec: AssetSpec, history: list[dict[str, str]], fund_daily: dict, event_lookup: dict,
              first_quote: dict, calendars: dict, index_map: dict, params: dict,
              us_weights: dict[int, D]) -> tuple[list, list, dict]:
    dates = [row["Date"] for row in history]
    if not dates or dates != sorted(set(dates)):
        raise ValueError(f"{spec.alias}: invalid processed asset calendar")
    unit_price = D(100)
    receivable = D(0)
    scheduled = defaultdict(lambda: {"verified": D(0), "modeled": D(0)})
    output, events = [], []
    basis_counts, flag_counts = defaultdict(int), defaultdict(int)
    unknown_dates, original_return_mismatches = [], []
    for index, original in enumerate(history):
        on = original["Date"]
        year = int(on[:4])
        total_return = D(original["Total Return"]) if original["Total Return"] else D(0)
        # Entries are (fund, contribution, cash basis, flag, verified pay,
        # modeled pay, payment basis). Every entitlement keeps its ex-date weight.
        legs = []
        if spec.alias == "USLCAP":
            value, basis, flag = index_map[on]
            legs.append(("INDEX", value, basis, flag, "", payment_model(on, 21), "assumed_index_lag_21_calendar_days"))
        else:
            is_observed = observed_source(spec, original["Quality Flag"])
            if spec.family == "gold":
                is_observed = on >= first_quote[spec.funds[0]]
            if is_observed:
                available = tuple(fund for fund in spec.funds
                                  if (fund, on) in fund_daily and fund_daily[fund, on]["Vendor Total Return"])
                if spec.family not in ("global_bond", "global_short_bond"):
                    available = spec.funds if (spec.funds[0], on) in fund_daily else ()
            else:
                available = spec.funds
            try:
                weights = blend_weights(spec, year, available, us_weights)
            except (ValueError, IndexError):
                # A missing observed leg is explicit, with a current-fund payout
                # model as the fallback. No synthetic observation is asserted.
                weights = blend_weights(spec, year, spec.funds, us_weights)
                is_observed = False
                unknown_dates.append(on)
            if is_observed and spec.family in ("global_bond", "global_short_bond"):
                combined = sum(weight * D(fund_daily[fund, on]["Vendor Total Return"])
                               for fund, weight in weights.items())
                if abs(total_return - combined) > D("0.00001"):
                    original_return_mismatches.append({"date": on, "return_difference": decimal_text(total_return - combined)})
            for fund, weight in weights.items():
                source = fund_daily.get((fund, on)) if is_observed else None
                event = event_lookup.get((fund, on)) if is_observed else None
                if source and source["Distribution Return"]:
                    contribution = D(source["Distribution Return"])
                    basis = "verified_zero" if source["Cash Status"] == "verified_zero_policy" else "observed"
                    flag = source["Cash Status"]
                    pay = event["Pay Date"] if event else ""
                    modeled_pay = (payment_model(on, params["fund_models"][fund]["seasonality"]["payment_lag_days"])
                                   if contribution and not pay else "")
                    pay_basis = "observed" if pay else "modeled_current_fund_payment_lag" if contribution else "not_applicable"
                else:
                    contribution, flag, modeled_pay = calendars[fund].get(
                        on, (D(0), "modeled_zero_routine_cash_policy" if spec.family == "gold" else "modeled_no_scheduled_payout", ""))
                    basis, pay, pay_basis = "modeled", "", "modeled_current_fund_payment_lag"
                    if is_observed:
                        flag = "modeled_source_cash_gap:" + flag
                        unknown_dates.append(on)
                legs.append((fund, weight * contribution, basis, flag, pay, modeled_pay, pay_basis))
        distribution = sum(leg[1] for leg in legs) if index else D(0)
        residual = total_return - distribution
        if 1 + residual <= 0:
            raise ValueError(f"{spec.alias} {on}: payout would make the synthetic unit nonpositive")
        previous_price = unit_price
        entitlement = previous_price * distribution
        unit_price *= 1 + residual
        receivable += entitlement
        if index:
            for fund, contribution, basis, flag, pay, modeled_pay, pay_basis in legs:
                if not contribution:
                    continue
                cash = previous_price * contribution
                effective = pay or modeled_pay
                if effective:
                    payment_index = bisect_left(dates, effective)
                    if payment_index < len(dates):
                        # Daily tables bucket nontrading payment dates into the
                        # next asset observation; the ledger retains actual dates.
                        scheduled[dates[payment_index]]["verified" if pay else "modeled"] += cash
                events.append({"Asset": spec.alias, "Ex Date": on, "Fund": fund,
                               "Distribution Return": decimal_text(contribution), "Cash USD Per Unit": decimal_text(cash),
                               "Pay Date": pay, "Modeled Pay Date": modeled_pay, "Payment Date Basis": pay_basis,
                               "Cash Basis": basis, "Quality Flag": flag,
                               "Model Version": params["version"] if basis == "modeled" or modeled_pay else ""})
        paid = scheduled[on]
        receivable -= paid["verified"] + paid["modeled"]
        if receivable < -D("0.000000001"):
            raise ValueError(f"{spec.alias}: payment ledger has negative receivables")
        leg_bases = sorted({leg[2] for leg in legs})
        basis = leg_bases[0] if len(leg_bases) == 1 else "mixed"
        flags = ";".join(sorted({leg[3] for leg in legs}))
        basis_counts[basis] += 1
        flag_counts[flags] += 1
        output.append({"Date": on, "Asset": spec.alias, "Currency": "USD", "Unit Price USD": decimal_text(unit_price),
                       "Total Return": original["Total Return"], "Distribution Return": decimal_text(distribution),
                       "Return Ex Distribution Residual": decimal_text(residual) if index else "",
                       "Cash Entitlement USD Per Unit": decimal_text(entitlement),
                       "Verified Cash Paid USD Per Unit": decimal_text(paid["verified"]),
                       "Modeled Cash Paid USD Per Unit": decimal_text(paid["modeled"]),
                       "Cash Receivable USD Per Unit": decimal_text(receivable), "Basis": basis, "Quality Flag": flags,
                       "Model Version": params["version"] if "modeled" in leg_bases else ""})
    return output, events, {"row_count": len(output), "first_date": dates[0], "last_date": dates[-1],
                            "basis_counts": dict(basis_counts), "quality_counts": dict(flag_counts),
                            "source_gap_dates": sorted(set(unknown_dates)),
                            "existing_return_source_differences": original_return_mismatches,
                            "unit_definition": UNIT_DEFINITION}
