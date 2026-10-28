"""Financial source cases: native units, duplicate payouts and source rejection."""

from datetime import datetime, timezone
from decimal import Decimal as D
import html
import io
import json

import openpyxl
import pytest

from src.distribution_sources import (CashEvent, COMPONENTS, day, parse_ishares, parse_proshares,
                                  parse_ssga_workbook, parse_vanguard, parse_yahoo)


def timestamp(day: str) -> int:
    return int(datetime.fromisoformat(day + "T15:00:00+00:00").timestamp())


def chart_payload(*, fund="UPRO", currency="USD", cash="0.5", split=False):
    stamps = [timestamp("2025-01-02"), timestamp("2025-01-03")]
    events = {"dividends": {str(stamps[1]): {"date": stamps[1], "amount": cash}}}
    if split:
        stamp = timestamp("2025-02-03")
        events["splits"] = {str(stamp): {"date": stamp, "numerator": 2, "denominator": 1}}
    return {"chart": {"error": None, "result": [{
        "meta": {"symbol": fund, "currency": currency, "exchangeTimezoneName": "America/New_York"},
        "timestamp": stamps, "indicators": {"quote": [{"close": [50, 49.5]}],
                                             "adjclose": [{"adjclose": [49.5, 49.5]}]}, "events": events,
    }]}}


def test_split_adjusted_vendor_cash_and_prices_recover_native_units():
    result = parse_yahoo(chart_payload(split=True), "UPRO")
    assert result.future_split_factor("2025-01-03") == 2
    assert result.as_paid_price("2025-01-02") == 100
    assert result.events[0].amount * result.future_split_factor(result.events[0].ex_date) == 1
    assert result.future_split_factor("2025-02-03") == 1


@pytest.mark.parametrize("kwargs", [{"fund": "VT"}, {"currency": "AUD"}])
def test_yahoo_rejects_wrong_identity_or_currency(kwargs):
    with pytest.raises(ValueError, match="symbol or currency"):
        parse_yahoo(chart_payload(**kwargs), "UPRO")


def test_overlap_dividend_capital_gain_alias_is_not_paid_twice():
    payload = chart_payload(cash="0.5")
    result = payload["chart"]["result"][0]
    stamp = result["timestamp"][1]
    result["events"]["capitalGains"] = {str(stamp): {"date": stamp, "amount": "0.2"}}
    # Adjustment factor implies 0.50 in total, not dividend-plus-gain 0.70.
    assert parse_yahoo(payload, "UPRO").events[0].amount == D("0.5")


def test_overlap_separate_cash_components_are_added_when_factor_supports_it():
    payload = chart_payload(cash="0.3")
    result = payload["chart"]["result"][0]
    stamp = result["timestamp"][1]
    result["events"]["capitalGains"] = {str(stamp): {"date": stamp, "amount": "0.2"}}
    assert parse_yahoo(payload, "UPRO").events[0].amount == D("0.5")


def test_ambiguous_overlap_stops_instead_of_inventing_cash():
    payload = chart_payload(cash="0.1")
    result = payload["chart"]["result"][0]
    stamp = result["timestamp"][1]
    result["events"]["capitalGains"] = {str(stamp): {"date": stamp, "amount": "0.2"}}
    with pytest.raises(ValueError, match="ambiguous"):
        parse_yahoo(payload, "UPRO")


def test_proshares_cash_components_preserve_precision_and_ignore_display_alias():
    event = parse_proshares([{"Symbol": "UPRO", "ExDate": "2025-03-26T00:00:00",
                             "CashDividendPerShare": "0.188372", "Dividend": "0.188372",
                             "LongTermCapGains": "0.020001", "PayableDate": "2025-04-01"}], "UPRO", "source")[0]
    assert event.amount == D("0.208373")
    assert event.components[COMPONENTS[0]] == D("0.188372")
    assert event.pay_date == "2025-04-01"
    assert event.declaration_date == ""


def test_vanguard_groups_income_and_gains_once():
    common = {"exDividendDate": "2018-04-02", "recordDate": "2018-04-03", "payableDate": "2018-04-05"}
    payload = [{**common, "typeCode": "INC", "amount": "0.181013"},
               {**common, "typeCode": "CGLT", "amount": "0.01916"}]
    event = parse_vanguard(payload, "BND", "source")[0]
    assert event.amount == D("0.200173")
    assert event.pay_date == "2018-04-05"
    with pytest.raises(ValueError, match="duplicate"):
        parse_vanguard(payload + [payload[0]], "BND", "source")


def test_ishares_embedded_history_uses_total_cash_including_capital_gains():
    values = {"exDate": [20211216], "recordDate": [20211217], "payableDate": [20211222],
              "incomeAmount": ["0.018007"], "shortTermCapitalGain": ["0.031906"],
              "longTermCapitalGain": ["0"], "returnOnCapital": ["0"],
              "totalDistribution": ["0.049913"]}
    points = {key: {"value": value} for key, value in values.items()}
    props = {"containersByNameMap": {"distributions": {"subContainersByNameMap": {
        "table": {"dataPointsByNameMap": points}}}}}
    document = f'<html><head><title>iShares fund | SHY</title></head><body>SHY<walrus-render-on-client componentprops="{html.escape(json.dumps(props))}"></walrus-render-on-client></body></html>'
    event = parse_ishares(document.encode(), "SHY", "source")[0]
    assert event.amount == D("0.049913")
    assert event.pay_date == "2021-12-22"
    assert day(20211216) == "2021-12-16"


def test_issuer_error_or_empty_markup_is_not_verified_zero():
    with pytest.raises(ValueError, match="no recognized"):
        parse_ishares(b"<html><title>Fund | SHY</title>SHY unavailable</html>", "SHY", "source")


def test_ssga_workbook_keeps_payout_components_and_filters_funds():
    book = openpyxl.Workbook()
    sheet = book.active
    sheet.title = "dividend"
    sheet.append(["TICKER", "EX-DATE", "RECORD DATE", "PAYABLE DATE", "DIVIDEND ($)",
                  "SHORT TERM CAPITAL GAIN ($)", "LONG TERM CAPITAL GAIN ($)"])
    sheet.append(["BWX", "12/20/2025", "12/20/2025", "12/26/2025", "0.123456", "0.01", ""])
    sheet.append(["OTHER", "12/20/2025", "12/20/2025", "12/26/2025", "999", "", ""])
    stream = io.BytesIO()
    book.save(stream)
    event = parse_ssga_workbook(stream.getvalue(), ("BWX",), "source")["BWX"][0]
    assert event.amount == D("0.133456")
    assert event.components[COMPONENTS[1]] == D("0.01")


@pytest.mark.parametrize("amount", [D("NaN"), D("Infinity"), D("-0.1")])
def test_invalid_cash_is_rejected(amount):
    with pytest.raises(ValueError, match="finite and nonnegative"):
        CashEvent("VT", "2025-03-21", amount, "source", "url").validate()
