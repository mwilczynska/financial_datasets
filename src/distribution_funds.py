"""Normalize source-fund cash and prices to native, as-paid USD share units."""

from __future__ import annotations

from dataclasses import replace
from decimal import Decimal, localcontext

try:
    from .distribution_sources import CashEvent, Chart, COMPONENTS, decimal_text, validate_issuer_event
except ImportError:
    from distribution_sources import CashEvent, Chart, COMPONENTS, decimal_text, validate_issuer_event

D = Decimal
EVENT_COLUMNS = [
    "Fund", "Currency", "Ex Date", "Record Date", "Pay Date", "Source Pay Date", "Declaration Date",
    "Cash USD Per Share", "Share Basis", *COMPONENTS, "Vendor Cash USD Per Share",
    "Previous Equivalent Price USD", "Distribution Return", "Source", "Source URL", "Quality Flag",
    "Reconciliation", "Source Notes",
]
PRICE_COLUMNS = [
    "Fund", "Date", "Price USD As Paid", "Split Ratio", "Quoted Price Return", "Vendor Total Return",
    "Distribution Return", "Cash Total Return", "Adjustment Residual", "Cash Status",
]


def close_enough(left: Decimal, right: Decimal) -> bool:
    return abs(left - right) <= max(D("0.0006"), abs(right) * D("0.0001"))


def normalize_fund(chart: Chart, issuer: list[CashEvent], end: str,
                   *, zero_policy: bool = False) -> tuple[list[dict[str, str]], list[dict[str, str]], dict]:
    """Union issuer/vendor events and retain every material disagreement.

    Issuer-reported cash has priority, while discrepancies remain explicit data.
    An issuer omission never silently deletes a vendor-reported special payout.
    Quoted price returns and vendor adjusted returns remain separate diagnostics.
    """
    dates = sorted(chart.quotes)
    prior_by_day = {current: prior for prior, current in zip(dates, dates[1:])}
    vendors = {event.ex_date: event for event in chart.events}
    if len(vendors) != len(chart.events):
        raise ValueError(f"{chart.fund}: duplicate vendor cash events")
    issuers = {event.ex_date: event for event in issuer}
    if len(issuers) != len(issuer):
        raise ValueError(f"{chart.fund}: duplicate issuer cash events")
    if zero_policy and (vendors or issuers):
        # Capture exceptional cash; historical zero is never a filter.
        zero_policy = False
    rows = []
    normalized: dict[str, dict[str, str]] = {}
    conflicts = []
    source_only = []
    for on in sorted(vendors.keys() | issuers.keys()):
        if on > end:
            # Announced future events are returned separately by the builder.
            continue
        vendor = vendors.get(on)
        supplied = issuers.get(on)
        factor = chart.future_split_factor(on)
        vendor_native = vendor.amount * factor if vendor else None
        if supplied:
            event = replace(supplied, components=dict(supplied.components))
            if factor != 1 and vendor and not close_enough(event.amount, vendor_native):
                if close_enough(event.amount, vendor.amount):
                    # Some issuer exports restate older events on adjusted units.
                    event.amount *= factor
                    event.components = {key: value * factor if value is not None else None
                                        for key, value in event.components.items()}
                    event.notes = (event.notes + " Issuer amount matched snapshot-adjusted vendor units; "
                                   "converted to original as-paid units using subsequent splits.").strip()
            event.share_basis = "as_paid"
            reconciliation = ("issuer_matches_vendor_rounding" if vendor and close_enough(event.amount, vendor_native)
                              else "issuer_vendor_amount_conflict" if vendor else "issuer_only_cash_event")
            if reconciliation == "issuer_vendor_amount_conflict":
                event.quality = "observed_issuer_vendor_conflict"
                conflicts.append({"ex_date": on, "issuer_usd": decimal_text(event.amount),
                                  "vendor_usd": decimal_text(vendor_native)})
            elif not vendor:
                source_only.append(on)
        else:
            event = replace(vendor, amount=vendor_native, share_basis="as_paid", components={})
            reconciliation = "vendor_cash_not_issuer_reconciled"
        event.validate()
        prior = prior_by_day.get(on)
        previous_equivalent = chart.quotes[prior]["close"] * factor if prior else None
        distribution = event.amount / previous_equivalent if previous_equivalent else None
        if on not in chart.quotes:
            event.quality = "observed_cash_quote_date_unresolved"
            event.notes += " Source ex-date has no matching fund quote; distribution return is unknown."
            previous_equivalent = distribution = None
        row = {
            "Fund": chart.fund, "Currency": "USD", "Ex Date": on, "Record Date": event.record_date,
            "Pay Date": event.pay_date, "Source Pay Date": event.source_pay_date,
            "Declaration Date": event.declaration_date, "Cash USD Per Share": decimal_text(event.amount),
            "Share Basis": "as_paid", **{key: decimal_text(event.components.get(key)) for key in COMPONENTS},
            "Vendor Cash USD Per Share": decimal_text(vendor_native),
            "Previous Equivalent Price USD": decimal_text(previous_equivalent),
            "Distribution Return": decimal_text(distribution), "Source": event.source,
            "Source URL": event.source_url, "Quality Flag": event.quality,
            "Reconciliation": reconciliation, "Source Notes": event.notes.strip(),
        }
        rows.append(row)
        normalized[on] = row
    prices = []
    unexplained = []
    split_map = {split.date: split.ratio for split in chart.splits}
    for on in dates:
        if on > end:
            continue
        current = chart.quotes[on]
        prior_day = prior_by_day.get(on)
        price_return = total_return = cash_return = residual = None
        payout = normalized.get(on)
        distribution = D(payout["Distribution Return"]) if payout and payout["Distribution Return"] else D(0)
        status = payout["Quality Flag"] if payout else "verified_zero_policy" if zero_policy else "observed_no_vendor_cash_event"
        if prior_day:
            previous = chart.quotes[prior_day]
            price_return = current["close"] / previous["close"] - 1
            total_return = current["adj"] / previous["adj"] - 1
            cash_return = price_return + distribution
            residual = total_return - cash_return
            # A material adjustment-factor jump without a cash event remains
            # unknown; do not manufacture a verified zero from a missing record.
            factor_implied = previous["close"] * (1 - (previous["adj"] / previous["close"])
                                                / (current["adj"] / current["close"]))
            if not payout and abs(factor_implied / previous["close"]) > D("0.00001"):
                status = "unknown_cash_adjustment_without_event"
                distribution = cash_return = residual = None
                unexplained.append(on)
        prices.append({"Fund": chart.fund, "Date": on,
                       "Price USD As Paid": decimal_text(chart.as_paid_price(on)),
                       "Split Ratio": decimal_text(split_map.get(on, D(1))),
                       "Quoted Price Return": decimal_text(price_return),
                       "Vendor Total Return": decimal_text(total_return),
                       "Distribution Return": decimal_text(distribution),
                       "Cash Total Return": decimal_text(cash_return),
                       "Adjustment Residual": decimal_text(residual), "Cash Status": status})
    diagnostics = {
        "fund": chart.fund, "first_quote": prices[0]["Date"], "last_quote": prices[-1]["Date"],
        "cash_event_count": len(rows), "issuer_event_count": sum(row["Source"] != "Yahoo chart cash events" for row in rows),
        "amount_conflicts": conflicts, "issuer_only_events": source_only,
        "unknown_adjustment_dates": unexplained,
        "missing_payment_dates": sum(not row["Pay Date"] for row in rows),
        "zero_policy": zero_policy,
    }
    return rows, prices, diagnostics
