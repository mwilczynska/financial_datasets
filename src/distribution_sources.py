"""Cash-event source contracts, corporate actions and public-source acquisition.

Cash amounts use Decimal throughout. Vendor prices and events are commonly
adjusted for subsequent splits: native amounts are reconstructed explicitly,
never by treating a rebased return index as a fund share price.
"""

from __future__ import annotations

import calendar
import io
import hashlib
import json
from dataclasses import dataclass, field
from datetime import date, datetime, time, timedelta, timezone
from decimal import Decimal, InvalidOperation
from pathlib import Path
from typing import Any
from urllib.parse import quote
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

import requests
from lxml import html


FUNDS = ("SHY", "IEF", "TLT", "VT", "BND", "BWX", "ISHG", "BWZ",
         "UPRO", "TYD", "TMF", "GLD", "UGL", "DBC", "SSO", "WLDU", "UST", "UBT")
# ProShares serves one distribution summary per fund and calendar year.
PROSHARES_FIRST_YEARS = {"UPRO": 2009, "SSO": 2006, "UST": 2010, "UBT": 2010}
# No machine-readable issuer history is published; Yahoo cash events are the source.
VENDOR_ONLY_FUNDS = frozenset(("WLDU",))
ZERO_POLICY_FUNDS = frozenset(("GLD", "UGL"))
COMPONENTS = ("Income USD Per Share", "Short Term Gains USD Per Share",
              "Long Term Gains USD Per Share", "Return Of Capital USD Per Share",
              "Special USD Per Share", "Other USD Per Share")
RIGHTS = "Third-party source terms apply; no blanket redistribution license is asserted."
D = Decimal


def number(value: Any, *, missing: bool = False) -> Decimal | None:
    """Parse finite, nonnegative USD cash, preserving the supplied precision."""
    if value is None or str(value).strip() in ("", "--", "-", "—", "–", "N/A"):
        if missing:
            return None
        raise ValueError("Missing cash amount")
    try:
        parsed = D(str(value).replace("$", "").replace(",", "").strip())
    except InvalidOperation as exc:
        raise ValueError(f"Invalid cash amount: {value!r}") from exc
    if not parsed.is_finite() or parsed < 0:
        raise ValueError(f"Cash amount must be finite and nonnegative: {value!r}")
    return parsed


def day(value: Any) -> str:
    if value is None or str(value).strip() in ("", "--", "N/A"):
        return ""
    if isinstance(value, (date, datetime)):
        return value.date().isoformat() if isinstance(value, datetime) else value.isoformat()
    text = str(value).strip()
    for fmt in ("%Y-%m-%d", "%Y%m%d", "%m/%d/%Y", "%m/%d/%y", "%b %d, %Y", "%B %d, %Y", "%d-%b-%Y"):
        try:
            return datetime.strptime(text[:10] if fmt == "%Y-%m-%d" else text, fmt).date().isoformat()
        except ValueError:
            pass
    raise ValueError(f"Unrecognized date: {value!r}")


def decimal_text(value: Decimal | None) -> str:
    if value is None:
        return ""
    # Fixed notation is important for machine readers and financial audit trails.
    text = format(value, "f")
    return text.rstrip("0").rstrip(".") if "." in text else text


@dataclass(frozen=True)
class Split:
    date: str
    ratio: Decimal  # New shares / old shares. A 1-for-10 reverse split is 0.1.


@dataclass
class CashEvent:
    fund: str
    ex_date: str
    amount: Decimal
    source: str
    source_url: str
    share_basis: str = "as_paid"
    record_date: str = ""
    pay_date: str = ""
    declaration_date: str = ""
    source_pay_date: str = ""
    components: dict[str, Decimal | None] = field(default_factory=dict)
    quality: str = "observed_issuer"
    notes: str = ""

    def validate(self) -> None:
        if self.fund not in FUNDS or not self.ex_date:
            raise ValueError("Event requires a supported fund and ex-date")
        day(self.ex_date)
        number(self.amount)
        if self.share_basis not in ("as_paid", "split_adjusted_to_snapshot", "unresolved"):
            raise ValueError(f"Unsupported share basis: {self.share_basis}")
        for name, value in self.components.items():
            if name not in COMPONENTS:
                raise ValueError(f"Unknown cash component: {name}")
            if value is not None:
                number(value)
        known = [value for value in self.components.values() if value is not None]
        if known and abs(sum(known, D(0)) - self.amount) > D("0.000002"):
            raise ValueError(f"{self.fund} {self.ex_date}: components do not sum to total cash")
        if self.pay_date and day(self.pay_date) < self.ex_date:
            raise ValueError(f"{self.fund} {self.ex_date}: payment {self.pay_date} precedes ex-date")
        if self.declaration_date and day(self.declaration_date) > self.ex_date:
            raise ValueError(f"{self.fund}: declaration follows ex-date")
        if self.record_date:
            day(self.record_date)


@dataclass
class Chart:
    fund: str
    quotes: dict[str, dict[str, Decimal]]
    events: list[CashEvent]
    splits: list[Split]
    as_of: str

    def future_split_factor(self, on: str) -> Decimal:
        factor = D(1)
        for split in self.splits:
            if split.date > on:
                factor *= split.ratio
        return factor

    def as_paid_price(self, on: str) -> Decimal:
        return self.quotes[on]["close"] * self.future_split_factor(on)


def validate_issuer_event(event: CashEvent) -> None:
    """Retain cash when one issuer date is contradictory; quarantine that date.

    An ex-date after payment can have special due-bill treatment, or simply be
    an issuer typo. Neither is silently assumed. Keep the source date as evidence
    and leave the usable payment date unknown until independently adjudicated.
    """
    event.source_pay_date = event.pay_date
    if event.pay_date and event.pay_date < event.ex_date:
        event.notes = (event.notes + f" Source payable date {event.pay_date} precedes ex-date; "
                       "payment date quarantined pending independent verification.").strip()
        event.pay_date = ""
        event.quality = "observed_issuer_payment_date_unresolved"
    event.validate()


def parse_yahoo(payload: dict, fund: str, url: str = "") -> Chart:
    error = payload.get("chart", {}).get("error")
    results = payload.get("chart", {}).get("result") or []
    if error or len(results) != 1:
        raise ValueError(f"Yahoo {fund}: missing chart or error: {error}")
    result = results[0]
    meta = result.get("meta", {})
    if meta.get("symbol") != fund or meta.get("currency") != "USD":
        raise ValueError(f"Yahoo {fund}: wrong symbol or currency")
    try:
        tz = ZoneInfo(meta.get("exchangeTimezoneName", "America/New_York"))
    except ZoneInfoNotFoundError:
        tz = timezone(timedelta(seconds=int(meta.get("gmtoffset", -18000))))
    local_day = lambda stamp: datetime.fromtimestamp(int(stamp), tz).date().isoformat()
    stamps = result.get("timestamp") or []
    closes = result.get("indicators", {}).get("quote", [{}])[0].get("close", [])
    adjusted = result.get("indicators", {}).get("adjclose", [{}])[0].get("adjclose", [])
    if not stamps or len(closes) != len(stamps) or len(adjusted) != len(stamps):
        raise ValueError(f"Yahoo {fund}: incomplete quote arrays")
    quotes = {}
    for stamp, close, adj in zip(stamps, closes, adjusted):
        if close is None or adj is None:
            continue
        on = local_day(stamp)
        if on in quotes:
            raise ValueError(f"Yahoo {fund}: duplicate quote date {on}")
        c, a = number(close), number(adj)
        if not c or not a:
            raise ValueError(f"Yahoo {fund}: nonpositive price")
        quotes[on] = {"close": c, "adj": a}
    if not quotes:
        raise ValueError(f"Yahoo {fund}: no valid prices")
    splits = []
    event_groups = result.get("events", {})
    for item in event_groups.get("splits", {}).values():
        numerator, denominator = number(item["numerator"]), number(item["denominator"])
        if not numerator or not denominator:
            raise ValueError(f"Yahoo {fund}: invalid split ratio")
        splits.append(Split(local_day(item["date"]), numerator / denominator))
    splits.sort(key=lambda item: item.date)
    if len({item.date for item in splits}) != len(splits):
        raise ValueError(f"Yahoo {fund}: duplicate split dates")
    # Yahoo may expose capital gains as a separate collection or include them in
    # dividends. Resolve overlap against adjustment factors; never blindly sum.
    by_day: dict[str, dict[str, Decimal]] = {}
    for kind in ("dividends", "capitalGains"):
        for item in event_groups.get(kind, {}).values():
            on = local_day(item["date"])
            if kind in by_day.setdefault(on, {}):
                raise ValueError(f"Yahoo {fund}: duplicate {kind} on {on}")
            by_day[on][kind] = number(item["amount"])
    dates = sorted(quotes)
    previous = {current: prior for prior, current in zip(dates, dates[1:])}
    events = []
    for on, amounts in sorted(by_day.items()):
        amount = sum(amounts.values(), D(0))
        notes = "Vendor event category does not establish the nature of the cash."
        if len(amounts) > 1:
            if on not in previous:
                raise ValueError(f"Yahoo {fund}: overlapping cash categories without a prior quote")
            prior = quotes[previous[on]]
            current = quotes[on]
            implied = prior["close"] * (1 - (prior["adj"] / prior["close"]) / (current["adj"] / current["close"]))
            candidates = sorted(set((*amounts.values(), amount)))
            ranked = sorted(candidates, key=lambda candidate: abs(candidate - implied))
            if abs(ranked[0] - implied) > max(D("0.0015"), abs(implied) * D("0.002")):
                raise ValueError(f"Yahoo {fund}: ambiguous overlapping cash categories on {on}")
            amount = ranked[0]
            notes += " Overlapping vendor categories resolved against the adjustment factor."
        if amount:
            events.append(CashEvent(fund, on, amount, "Yahoo chart cash events", url,
                                    share_basis="split_adjusted_to_snapshot",
                                    quality="observed_vendor_rounded", notes=notes))
    return Chart(fund, quotes, events, splits, max(quotes))


class SourceCache:
    """Response cache with hashes and successful-delivery evidence.

    Error documents never replace a previously validated cache. Callers validate
    content before accept(); HTTP 200 by itself is not source acceptance.
    """

    def __init__(self, root: Path, *, offline: bool = False, session: Any = None):
        self.root = root
        self.directory = root / "sources/raw/distributions"
        self.directory.mkdir(parents=True, exist_ok=True)
        self.offline = offline
        self.session = session or requests.Session()
        self.session.headers.update({"User-Agent": "Mozilla/5.0"})
        self.records: dict[str, dict] = {}

    def get(self, key: str, url: str, *, params: dict | None = None, refresh: bool = False) -> tuple[bytes, dict]:
        path = self.directory / key
        record_path = self.directory / (key + ".retrieval.json")
        if path.exists() and (self.offline or not refresh):
            content = path.read_bytes()
            if not record_path.exists():
                raise ValueError(f"Source cache {key} has no retrieval record")
            record = json.loads(record_path.read_text(encoding="utf-8"))
            if record["sha256"] != hashlib.sha256(content).hexdigest():
                raise ValueError(f"Source cache checksum mismatch: {key}")
            return content, record
        if self.offline:
            raise FileNotFoundError(f"Offline source cache is missing: {key}")
        response = self.session.get(url, params=params, timeout=45)
        content = response.content
        objects = self.directory / "objects"
        objects.mkdir(exist_ok=True)
        archive = objects / hashlib.sha256(content).hexdigest()
        if not archive.exists():
            archive.write_bytes(content)
        record = {"url": response.url, "retrieved_at_utc": datetime.now(timezone.utc).isoformat(),
                  "sha256": hashlib.sha256(content).hexdigest(), "http_status": response.status_code,
                  "path": archive.relative_to(self.root).as_posix(), "rights": RIGHTS, "accepted": False}
        self.records[key] = record
        response.raise_for_status()
        return content, record

    def accept(self, key: str, content: bytes, record: dict, **coverage: Any) -> None:
        objects = self.directory / "objects"
        objects.mkdir(exist_ok=True)
        archive = objects / record["sha256"]
        if not archive.exists():
            archive.write_bytes(content)
        record = {**record, **coverage, "cache_key": key, "accepted": True,
                  "path": archive.relative_to(self.root).as_posix()}
        (self.directory / key).write_bytes(content)
        (self.directory / (key + ".retrieval.json")).write_text(
            json.dumps(record, indent=2, sort_keys=True) + "\n", encoding="utf-8")
        self.records[key] = record


def yahoo_chart(cache: SourceCache, fund: str, start: date, end: date, *, refresh: bool) -> Chart:
    stamp = lambda value: int(datetime.combine(value, time.min, tzinfo=timezone.utc).timestamp())
    # Include corporate actions through retrieval day, including splits after a
    # deliberately earlier output end date. Prices are adjusted to the snapshot.
    delivery_end = max(end, datetime.now(timezone.utc).date())
    url = f"https://query1.finance.yahoo.com/v8/finance/chart/{quote(fund, safe='')}"
    params = {"period1": stamp(start), "period2": stamp(delivery_end + timedelta(days=1)),
              "interval": "1d", "events": "div,splits,capitalGains", "includeAdjustedClose": "true"}
    key = f"yahoo_{fund.replace('^', '')}_{start.isoformat()}.json"
    if cache.offline and not (cache.directory / key).exists():
        full_key = f"yahoo_{fund.replace('^', '')}_1970-01-01.json"
        if (cache.directory / full_key).exists():
            key = full_key
    content, record = cache.get(key, url, params=params, refresh=refresh)
    chart = parse_yahoo(json.loads(content), fund, record["url"])
    if chart.as_of < (end - timedelta(days=5)).isoformat():
        raise ValueError(f"Yahoo {fund}: stale quote coverage {chart.as_of} for {end}")
    cache.accept(key, content, record, first_quote=min(chart.quotes), last_quote=max(chart.quotes),
                 quote_count=len(chart.quotes), cash_events=len(chart.events),
                 split_events=len(chart.splits), currency="USD")
    return chart


def parse_ishares(content: bytes, fund: str, url: str) -> list[CashEvent]:
    document = html.fromstring(content)
    titles = " ".join(document.xpath("//title/text()"))
    if fund not in titles.split("|")[-1].strip().split():
        raise ValueError(f"iShares: response does not identify {fund}")
    for element in document.xpath("//*[@componentprops]"):
        props = json.loads(element.get("componentprops"))
        container = props.get("containersByNameMap", {}).get("distributions", {})
        points = container.get("subContainersByNameMap", {}).get("table", {}).get("dataPointsByNameMap", {})
        if not points:
            continue
        values = {key: item.get("value", item.get("formattedValue", [])) for key, item in points.items()}
        if "totalDistribution" not in values:
            raise ValueError(f"iShares {fund}: missing total distribution field")
        # The column key names are checked explicitly below once the delivery is
        # normalized; unequal arrays must not silently truncate an event history.
        required = ("exDate", "recordDate", "payableDate", "totalDistribution")
        if any(key not in values for key in required):
            raise ValueError(f"iShares {fund}: missing distribution columns: {sorted(values)}")
        count = len(values["exDate"])
        if any(len(values[key]) != count for key in required):
            raise ValueError(f"iShares {fund}: unequal distribution arrays")
        events = []
        component_keys = {"incomeAmount": COMPONENTS[0], "shortTermCapitalGain": COMPONENTS[1],
                          "longTermCapitalGain": COMPONENTS[2], "returnOnCapital": COMPONENTS[3]}
        if any(len(values[key]) != count for key in component_keys if key in values):
            raise ValueError(f"iShares {fund}: unequal component arrays")
        for index in range(count):
            amount = number(values["totalDistribution"][index])
            if not amount:
                continue
            components = {name: number(values[key][index], missing=True)
                          for key, name in component_keys.items() if key in values}
            event = CashEvent(fund, day(values["exDate"][index]), amount, "iShares distribution history", url,
                              record_date=day(values["recordDate"][index]),
                              pay_date=day(values["payableDate"][index]), components=components)
            validate_issuer_event(event)
            events.append(event)
        return sorted(events, key=lambda event: event.ex_date)
    raise ValueError(f"iShares {fund}: no recognized distribution history")


def parse_proshares(payload: list, fund: str, url: str) -> list[CashEvent]:
    if not isinstance(payload, list):
        raise ValueError(f"ProShares {fund}: response is not an event array")
    result = []
    keys = ("CashDividendPerShare", "ShortTermCapGains", "LongTermCapGains", "ReturnOfCapital",
            "SpecialPerShare", "OtherPerShare")
    for item in payload:
        if item.get("Symbol", "").upper() != fund:
            raise ValueError(f"ProShares: wrong fund in {fund} response")
        components = {name: number(item.get(key), missing=True) for key, name in zip(keys, COMPONENTS)}
        amount = sum((value for value in components.values() if value is not None), D(0))
        # Dividend is a display alias, not another component to add.
        if not amount and item.get("Dividend") is not None:
            amount = number(item["Dividend"])
            components = {}
        if not amount:
            continue
        event = CashEvent(fund, day(item["ExDate"]), amount, "ProShares distribution summary", url,
                          record_date=day(item.get("RecordDate")), pay_date=day(item.get("PayableDate")),
                          components=components)
        validate_issuer_event(event)
        result.append(event)
    return sorted(result, key=lambda event: event.ex_date)


def parse_ssga_workbook(content: bytes, funds: tuple[str, ...], url: str) -> dict[str, list[CashEvent]]:
    import openpyxl

    book = openpyxl.load_workbook(io.BytesIO(content), read_only=True, data_only=True)
    result: dict[str, list[CashEvent]] = {fund: [] for fund in funds}
    try:
        if "dividend" not in book.sheetnames:
            raise ValueError("State Street: missing dividend worksheet")
        rows = iter(book["dividend"].values)
        header = [str(value).strip() for value in next(rows)]
        expected = ("TICKER", "EX-DATE", "RECORD DATE", "PAYABLE DATE", "DIVIDEND ($)",
                    "SHORT TERM CAPITAL GAIN ($)", "LONG TERM CAPITAL GAIN ($)")
        if any(name not in header for name in expected):
            raise ValueError(f"State Street: unsupported distribution headers {header}")
        for values in rows:
            row = dict(zip(header, values))
            fund = str(row.get("TICKER", "")).strip()
            if fund not in result:
                continue
            components = {name: number(row[key], missing=True) for key, name in zip(
                ("DIVIDEND ($)", "SHORT TERM CAPITAL GAIN ($)", "LONG TERM CAPITAL GAIN ($)"), COMPONENTS)}
            amount = sum((value for value in components.values() if value is not None), D(0))
            if not amount:
                continue
            event = CashEvent(fund, day(row["EX-DATE"]), amount, "State Street historical distributions", url,
                              record_date=day(row["RECORD DATE"]), pay_date=day(row["PAYABLE DATE"]),
                              components=components)
            validate_issuer_event(event)
            result[fund].append(event)
    finally:
        book.close()
    for fund, events in result.items():
        if not events:
            raise ValueError(f"State Street: no distribution rows for {fund}")
        result[fund] = sorted(events, key=lambda event: event.ex_date)
    return result


def parse_vanguard(payload: list, fund: str, url: str) -> list[CashEvent]:
    if not isinstance(payload, list):
        raise ValueError(f"Vanguard {fund}: response is not an event array")
    kinds = {"INC": COMPONENTS[0], "CGST": COMPONENTS[1], "CGLT": COMPONENTS[2], "ROC": COMPONENTS[3]}
    grouped: dict[str, CashEvent] = {}
    seen: set[tuple[str, str]] = set()
    for item in payload:
        on = day(item["exDividendDate"])
        kind = item["typeCode"]
        if (on, kind) in seen:
            raise ValueError(f"Vanguard {fund}: duplicate {kind} on {on}")
        seen.add((on, kind))
        amount = number(item["amount"])
        if not amount:
            continue
        event = grouped.setdefault(on, CashEvent(fund, on, D(0), "Vanguard distribution history", url,
                                                 record_date=day(item.get("recordDate")),
                                                 pay_date=day(item.get("payableDate"))))
        if (event.record_date != day(item.get("recordDate"))
                or event.pay_date != day(item.get("payableDate"))):
            raise ValueError(f"Vanguard {fund}: same-ex-date components have different dates")
        name = kinds.get(kind, COMPONENTS[5])
        event.components[name] = event.components.get(name, D(0)) + amount
        event.amount += amount
    for event in grouped.values():
        validate_issuer_event(event)
    return sorted(grouped.values(), key=lambda event: event.ex_date)


def parse_direxion(content: bytes, fund: str, url: str) -> list[CashEvent]:
    document = html.fromstring(content)
    # Joint bull/bear pages contain several fund tables; scope the table to its
    # own heading rather than accepting the first distribution table on a page.
    for heading in document.xpath("//h2|//h3|//h4"):
        text = " ".join(heading.text_content().split())
        if not text.startswith(fund + " "):
            continue
        tables = heading.xpath("following::table[1]")
        if not tables:
            continue
        table = tables[0]
        header = " ".join(table.xpath(".//tr[1]")[0].text_content().split())
        if not all(name in header for name in ("Record Date", "Ex Date", "Pay Date", "Income Dividend")):
            continue
        events = []
        for row in table.xpath(".//tr[td]"):
            cells = [" ".join(cell.text_content().split()) for cell in row.xpath("./td")]
            if len(cells) < 6:
                continue
            components = {name: number(value, missing=True) for name, value in zip(COMPONENTS, cells[3:6])}
            amount = sum((value for value in components.values() if value is not None), D(0))
            if amount:
                event = CashEvent(fund, day(cells[1]), amount, "Direxion distribution history", url,
                                  record_date=day(cells[0]), pay_date=day(cells[2]), components=components)
                validate_issuer_event(event)
                events.append(event)
        if events:
            return sorted(events, key=lambda event: event.ex_date)
    raise ValueError(f"Direxion {fund}: no recognized fund-specific distribution table")


ISHARES_URLS = {
    "SHY": "https://www.ishares.com/us/products/239452/ishares-13-year-treasury-bond-etf",
    "IEF": "https://www.ishares.com/us/products/239456/ishares-710-year-treasury-bond-etf",
    "TLT": "https://www.ishares.com/us/products/239454/ishares-20-year-treasury-bond-etf",
    "ISHG": "https://www.ishares.com/us/products/239829/ishares-13-year-international-treasury-bond-etf",
}
VANGUARD_IDS = {"VT": "3141", "BND": "0928"}
SSGA_URL = "https://www.ssga.com/library-content/products/fund-data/etfs/us/spdr-etf-historical-distributions.xlsx"
DIREXION_URLS = {
    "TYD": "https://www.direxion.com/product/daily-7-10-year-treasury-bull-bear-3x-etfs",
    "TMF": "https://www.direxion.com/product/daily-20-year-treasury-bull-bear-3x-etfs",
}


def issuer_events(cache: SourceCache, funds: tuple[str, ...], end: date, *, refresh: bool,
                  full: bool = False) -> tuple[dict[str, list[CashEvent]], dict[str, dict]]:
    """Retrieve public issuer histories once per shared delivery route.

    Provider failures are explicit. The caller decides whether a documented
    vendor fallback is sufficient; a failed response is never accepted as zero.
    """
    events: dict[str, list[CashEvent]] = {}
    evidence: dict[str, dict] = {}

    def accept(key: str, content: bytes, record: dict, parsed: dict[str, list[CashEvent]]) -> None:
        cache.accept(key, content, record, fund_event_counts={fund: len(items) for fund, items in parsed.items()})
        for fund, items in parsed.items():
            events.setdefault(fund, []).extend(items)
            evidence.setdefault(fund, {"delivery": "available", "sources": []})["sources"].append(key)

    for fund in funds:
        if fund not in ISHARES_URLS and fund not in VANGUARD_IDS:
            continue
        url = ISHARES_URLS.get(fund) or (
            "https://advisors.vanguard.com/investments/products/api/funds/"
            f"{VANGUARD_IDS[fund]}/pricing/distributions?hasDistributionYield=true")
        key = f"issuer_{fund}.html" if fund in ISHARES_URLS else f"issuer_{fund}.json"
        try:
            content, record = cache.get(key, url, refresh=refresh)
            parsed = (parse_ishares(content, fund, record["url"]) if fund in ISHARES_URLS
                      else parse_vanguard(json.loads(content), fund, record["url"]))
            if not parsed:
                raise ValueError(f"Issuer {fund}: unexpectedly empty paying-fund history")
            accept(key, content, record, {fund: parsed})
        except (requests.RequestException, ValueError, FileNotFoundError) as exc:
            evidence[fund] = {"delivery": "unavailable", "error": str(exc)}
    if "DBC" in funds:
        # The public page currently delivers a dynamic shell or HTTP 406. Keep
        # the actual attempt and its hash; neither establishes a zero payout.
        # Attributed issuer notices below supplement the vendor event history.
        key = "issuer_DBC.html"
        url = "https://www.invesco.com/us/en/financial-products/etfs/invesco-db-commodity-index-tracking-fund.html"
        try:
            content, record = cache.get(key, url, refresh=refresh)
            evidence["DBC"] = {"delivery": "unavailable_dynamic_history", "source_url": record["url"],
                               "response_sha256": record["sha256"],
                               "error": "No validated machine-readable DBC distribution history in this delivery; use labeled vendor/notice coverage."}
        except (requests.RequestException, ValueError, FileNotFoundError) as exc:
            evidence["DBC"] = {"delivery": "unavailable", "source_url": url, "error": str(exc)}
    for fund in ZERO_POLICY_FUNDS.intersection(funds):
        evidence[fund] = {"delivery": "documented_zero_routine_policy", "sources": [],
                          "policy_evidence": "sources/derived/distribution_cash_policies.json",
                          "exceptional_cash_ingestion": True}
    ssga_funds = tuple(fund for fund in funds if fund in ("BWX", "BWZ"))
    if ssga_funds:
        key = "issuer_ssga_distributions.xlsx"
        try:
            content, record = cache.get(key, SSGA_URL, refresh=refresh)
            accept(key, content, record, parse_ssga_workbook(content, ssga_funds, record["url"]))
        except (requests.RequestException, ValueError, FileNotFoundError) as exc:
            for fund in ssga_funds:
                evidence[fund] = {"delivery": "unavailable", "error": str(exc)}
    for fund, first_year in PROSHARES_FIRST_YEARS.items():
        if fund not in funds:
            continue
        # Numeric years are the provider's supported requests; "all" returns an
        # error page. Normal refreshes fetch two recent calendar years; periodic
        # full checks also refetch older years to detect retrospective revisions.
        for year in range(first_year if full else max(first_year, end.year - 1), end.year + 1):
            key = f"issuer_{fund}_{year}.json"
            url = f"https://www.proshares.com/api/distributionsummary/?fund={fund}&year={year}"
            try:
                content, record = cache.get(key, url, refresh=refresh and (full or year >= end.year - 1))
                parsed = parse_proshares(json.loads(content), fund, record["url"])
                accept(key, content, record, {fund: parsed})
            except (requests.RequestException, ValueError, FileNotFoundError) as exc:
                evidence.setdefault(fund, {"delivery": "partial", "sources": []})
                evidence[fund]["delivery"] = "partial"
                evidence[fund].setdefault("errors", []).append({"year": year, "error": str(exc)})
    for fund in VENDOR_ONLY_FUNDS.intersection(funds):
        evidence[fund] = {"delivery": "vendor_only_no_issuer_history", "sources": []}
    for fund in funds:
        if fund not in DIREXION_URLS:
            continue
        key, url = f"issuer_{fund}.html", DIREXION_URLS[fund]
        try:
            content, record = cache.get(key, url, refresh=refresh)
            accept(key, content, record, {fund: parse_direxion(content, fund, record["url"])})
        except (requests.RequestException, ValueError, FileNotFoundError) as exc:
            evidence[fund] = {"delivery": "unavailable", "error": str(exc)}
    # Small, explicitly transcribed primary-source observations are a fallback
    # when a provider blocks automated delivery. They do not imply full coverage
    # or substitute for future live refreshes. Raw source dates are preserved.
    observations = cache.root / "sources/derived/distribution_issuer_observations.csv"
    if observations.exists():
        import csv
        with observations.open(encoding="utf-8", newline="") as handle:
            for row in csv.DictReader(handle):
                fund = row["Fund"]
                if fund not in funds:
                    continue
                event = CashEvent(fund, day(row["Ex Date"]), number(row["Cash USD Per Share"]),
                                  row["Source"], row["Source URL"], record_date=day(row["Record Date"]),
                                  pay_date=day(row["Pay Date"]),
                                  components={name: number(row.get(name), missing=True) for name in COMPONENTS},
                                  quality="observed_primary_transcribed",
                                  notes=f"Primary-source observation verified {row['Verified Date']}; partial coverage.")
                validate_issuer_event(event)
                existing = {item.ex_date for item in events.get(fund, [])}
                if event.ex_date not in existing:
                    events.setdefault(fund, []).append(event)
        digest = hashlib.sha256(observations.read_bytes()).hexdigest()
        cache.records["primary_observations"] = {
            "path": observations.relative_to(cache.root).as_posix(), "sha256": digest,
            "accepted": True, "method": "Transcribed and attributed primary financial facts; partial coverage.",
            "rights": RIGHTS, "verified_date": "2026-10-28"}
    policy_path = cache.root / "sources/derived/distribution_cash_policies.json"
    if policy_path.exists():
        cache.records["cash_policy_evidence"] = {
            "path": policy_path.relative_to(cache.root).as_posix(),
            "sha256": hashlib.sha256(policy_path.read_bytes()).hexdigest(),
            "accepted": True, "rights": RIGHTS}
    return events, evidence
