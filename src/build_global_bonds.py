"""Build an unhedged global sovereign/aggregate bond total-return proxy dataset.

The 1970-2007 segment reconstructs a daily total-return *path* from observed daily FX
(BIS) and observed monthly long-term government-bond yields (OECD MEI), GDP-weighted
across 16 advanced economies, then rescales each calendar year so the year matches the
Jorda-Schularick-Taylor (JST) annual global government-bond basket exactly. JST supplies
the authoritative annual level anchor; the FX + yield reconstruction supplies the path.
From the BND/BWX overlap onward the dataset uses an observed 45/55 daily-rebalanced blend.
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import math
import re
from datetime import date, datetime, time, timedelta, timezone
from decimal import Decimal, getcontext
from io import BytesIO
from pathlib import Path
from zipfile import ZipFile
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError
from xml.etree import ElementTree as ET

import requests

getcontext().prec = 40

ASSET_ID = "global_bonds"
ASSET_NAME = "Unhedged Global Bonds Total-Return Proxy"
ALIAS = "GLBOND"

START_DATE = date(1970, 1, 1)
ETF_BLEND_START = date(2007, 10, 11)
JST_URL = "https://www.macrohistory.net/app/download/9834512569/JSTdatasetR6.xlsx?t=1720600177"
BND_SYMBOL = "BND"
BWX_SYMBOL = "BWX"
BND_WEIGHT = Decimal("0.45")
BWX_WEIGHT = Decimal("0.55")

# DBnomics public JSON API (no key). Provider/dataset/series path form.
DBNOMICS_URL = "https://api.db.nomics.world/v22/series/{provider}/{dataset}/{series}?observations=1"

# JST iso3 -> (BIS ref-area, BIS currency code). USA needs no FX conversion (factor 1).
# Euro-legacy countries use the chained `.EUR.` series (BIS splices the legacy currency
# into the euro series), so their daily FX still reaches back to the 1950s-1960s.
COUNTRY_FX: dict[str, tuple[str, str] | None] = {
    "USA": None,
    "DEU": ("DE", "EUR"),
    "JPN": ("JP", "JPY"),
    "GBR": ("GB", "GBP"),
    "CAN": ("CA", "CAD"),
    "FRA": ("FR", "EUR"),
    "AUS": ("AU", "AUD"),
    "ITA": ("IT", "EUR"),
    "NLD": ("NL", "EUR"),
    "CHE": ("CH", "CHF"),
    "SWE": ("SE", "SEK"),
    "ESP": ("ES", "EUR"),
    "DNK": ("DK", "DKK"),
    "NOR": ("NO", "NOK"),
    "FIN": ("FI", "EUR"),
    "BEL": ("BE", "EUR"),
}
COUNTRIES = list(COUNTRY_FX.keys())
BOND_MATURITY_YEARS = 10.0  # OECD IRLTLT01 is the 10-year long-term government bond yield.

# Genuine daily bond-return sources for the three largest weights (others stay monthly):
#   USA -> in-repo daily 7-10y Treasury total return (Fed yield-curve model -> IEF).
#   JPN -> MoF daily 10y JGB yield (continuous from 1986-07).
#   GBR -> BoE GLC daily 10y nominal spot yield (from 1979).
ITT_CSV_NAME = "intermediate_term_us_treasury.csv"
MOF_JGB_URL = "https://www.mof.go.jp/jgbs/reference/interest_rate/data/jgbcm_all.csv"
BOE_GLC_URL = "https://www.bankofengland.co.uk/-/media/boe/files/statistics/yield-curves/glcnominalddata.zip"
DAILY_RATE_COUNTRIES = ("USA", "JPN", "GBR")
EXCEL_EPOCH = date(1899, 12, 30)

YAHOO_COLUMNS = ["Date", "Open", "High", "Low", "Close", "Adj Close", "Volume"]
PROJECT_COLUMNS = ["Price Return", "Total Return", "Source", "Quality Flag", "Source Notes"]
OUTPUT_COLUMNS = YAHOO_COLUMNS + PROJECT_COLUMNS

EARLY_FLAG = "model_jst_anchored_daily_fx_monthly_yield_global_govt_bond_unhedged"
ETF_BLEND_FLAG = "observed_bnd_bwx_unhedged_daily_rebalanced_proxy"

EARLY_SOURCE = "JST annual anchor + BIS daily FX + OECD MEI monthly 10y government-bond yields"
ETF_BLEND_SOURCE = "Yahoo Finance chart API (BND + BWX adjusted-close total returns)"

EARLY_NOTES = (
    "Unhedged USD global government-bond model. Daily path = GDP-weighted basket of "
    "observed daily FX returns (BIS, local currency per USD) and bond total returns, "
    "rescaled so each calendar year matches the JST annual global government-bond basket. "
    "Bond returns are genuinely daily for the US (in-repo 7-10y Treasury TR, 1970+), Japan "
    "(MoF 10y JGB, 1986-07+) and the UK (BoE 10y nominal spot, 1979+); other countries and "
    "earlier years use OECD MEI monthly 10y yields (par-bond reprice + carry) smoothed "
    "within month. Annual level is anchored to JST."
)
ETF_BLEND_NOTES = (
    "Daily passive unhedged proxy: 45% BND U.S. aggregate bonds + 55% BWX international "
    "treasury bonds in local currencies, rebalanced daily from adjusted-close returns."
)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--end-date", default=date.today().isoformat(), help="Inclusive end date, YYYY-MM-DD.")
    parser.add_argument("--root", default=".", help="Project root.")
    parser.add_argument(
        "--refresh-static-sources",
        action="store_true",
        help="Refetch historical JST/BIS/OECD/MoF/BoE inputs instead of reusing cached raw files.",
    )
    return parser.parse_args()


def unix_seconds(day: date) -> int:
    return int(datetime.combine(day, time.min, tzinfo=timezone.utc).timestamp())


def log(message: str) -> None:
    print(message, flush=True)


def cached_binary(raw_dir: Path, filename: str, url: str, refresh: bool, label: str) -> bytes:
    path = raw_dir / filename
    if path.exists() and not refresh:
        log(f"Using cached {label}: {path}")
        return path.read_bytes()
    log(f"Fetching {label} ...")
    content = fetch_binary(url)
    path.write_bytes(content)
    log(f"Cached {label}: {path} ({len(content):,} bytes)")
    return content


def fetch_binary(url: str) -> bytes:
    response = requests.get(url, timeout=60, headers={"User-Agent": "Mozilla/5.0"})
    response.raise_for_status()
    return response.content


def fetch_chart(symbol: str, end_date: date, start_date: date = START_DATE) -> dict:
    period1 = unix_seconds(start_date)
    period2 = unix_seconds(end_date + timedelta(days=1))
    url = (
        f"https://query1.finance.yahoo.com/v8/finance/chart/{symbol}"
        f"?period1={period1}&period2={period2}&interval=1d&events=history&includeAdjustedClose=true"
    )
    response = requests.get(url, timeout=60, headers={"User-Agent": "Mozilla/5.0"})
    response.raise_for_status()
    payload = response.json()
    error = payload.get("chart", {}).get("error")
    if error:
        raise RuntimeError(f"Yahoo chart error for {symbol}: {error}")
    return payload


def fetch_dbnomics(provider: str, dataset: str, series_code: str) -> dict:
    url = DBNOMICS_URL.format(provider=provider, dataset=dataset, series=series_code)
    response = requests.get(url, timeout=60, headers={"User-Agent": "Mozilla/5.0"})
    response.raise_for_status()
    return response.json()


def dbnomics_observations(payload: dict) -> dict[str, float]:
    """Return {period: value} for the first series doc, dropping nulls."""
    docs = payload.get("series", {}).get("docs", [])
    if not docs:
        return {}
    doc = docs[0]
    periods = doc.get("period", []) or []
    values = doc.get("value", []) or []
    result: dict[str, float] = {}
    for period, value in zip(periods, values):
        if value is None:
            continue
        try:
            result[period] = float(value)
        except (TypeError, ValueError):
            continue
    return result


def fetch_bis_fx(raw_dir: Path, refresh_static_sources: bool = False) -> dict[str, dict[str, float]]:
    """Daily FX levels (local currency per USD) per country from BIS WS_XRU via DBnomics."""
    cache_path = raw_dir / f"{ASSET_ID}_bis_fx.json"
    if cache_path.exists() and not refresh_static_sources:
        log(f"Using cached BIS FX: {cache_path}")
        raw = json.loads(cache_path.read_text(encoding="utf-8"))
        return {iso: dbnomics_observations(payload) for iso, payload in raw.items()}

    log("Fetching BIS daily FX via DBnomics ...")
    raw: dict[str, dict] = {}
    levels: dict[str, dict[str, float]] = {}
    for iso, fx in COUNTRY_FX.items():
        if fx is None:
            continue
        area, currency = fx
        series_code = f"D.{area}.{currency}.A"
        log(f"  BIS {iso} {series_code}")
        payload = fetch_dbnomics("BIS", "WS_XRU", series_code)
        raw[iso] = payload
        levels[iso] = dbnomics_observations(payload)
    cache_path.write_text(json.dumps(raw), encoding="utf-8")
    return levels


def fetch_oecd_yields(raw_dir: Path, refresh_static_sources: bool = False) -> dict[str, dict[str, float]]:
    """Monthly 10y government-bond yields (decimal) per country from OECD MEI via DBnomics."""
    cache_path = raw_dir / f"{ASSET_ID}_oecd_yields.json"
    if cache_path.exists() and not refresh_static_sources:
        log(f"Using cached OECD 10y yields: {cache_path}")
        raw = json.loads(cache_path.read_text(encoding="utf-8"))
        return {iso: {period: value / 100.0 for period, value in dbnomics_observations(payload).items()}
                for iso, payload in raw.items()}

    log("Fetching OECD monthly 10y yields via DBnomics ...")
    raw: dict[str, dict] = {}
    yields: dict[str, dict[str, float]] = {}
    for iso in COUNTRIES:
        series_code = f"{iso}.IRLTLT01.ST.M"
        log(f"  OECD {iso} {series_code}")
        payload = fetch_dbnomics("OECD", "MEI", series_code)
        raw[iso] = payload
        # OECD MEI long-term rate is in percent per annum; convert to decimal.
        yields[iso] = {period: value / 100.0 for period, value in dbnomics_observations(payload).items()}
    cache_path.write_text(json.dumps(raw), encoding="utf-8")
    return yields


def _japanese_era_to_iso(value: str) -> str | None:
    """Convert a JST CSV date like 'S49.9.24' / 'H1.1.4' / 'R3.4.1' to ISO."""
    match = re.match(r"\s*([SHR])(\d+)\.(\d+)\.(\d+)\s*$", value)
    if not match:
        return None
    base = {"S": 1925, "H": 1988, "R": 2018}[match.group(1)]
    year = base + int(match.group(2))
    return f"{year:04d}-{int(match.group(3)):02d}-{int(match.group(4)):02d}"


def parse_mof_jgb_10y(content: bytes) -> dict[str, float]:
    """Parse daily 10-year JGB yields (decimal) from the Japanese MoF historical CSV."""
    lines = [line for line in content.decode("cp932", errors="replace").splitlines() if line.strip()]
    header = lines[1].split(",")  # row 1 holds maturity labels; row 0 is a title
    ten_year_index = next(i for i, label in enumerate(header) if label.strip().startswith("10"))
    yields: dict[str, float] = {}
    for line in lines[2:]:
        cells = line.split(",")
        iso = _japanese_era_to_iso(cells[0])
        if iso is None or len(cells) <= ten_year_index:
            continue
        raw_value = cells[ten_year_index].strip()
        if raw_value in ("", "-"):
            continue
        yields[iso] = float(raw_value) / 100.0
    return yields


def fetch_mof_jgb_10y(raw_dir: Path, refresh_static_sources: bool = False) -> dict[str, float]:
    """Daily 10-year JGB yields (decimal) from the Japanese MoF historical CSV."""
    content = cached_binary(raw_dir, f"{ASSET_ID}_mof_jgb.csv", MOF_JGB_URL, refresh_static_sources, "MoF JGB yield CSV")
    return parse_mof_jgb_10y(content)


def parse_boe_workbook_10y(workbook_bytes: bytes) -> dict[str, float]:
    """Extract daily 10y nominal spot yields (decimal) from one BoE GLC workbook."""
    namespace = {"a": "http://schemas.openxmlformats.org/spreadsheetml/2006/main"}
    rel_ns = "{http://schemas.openxmlformats.org/officeDocument/2006/relationships}"
    with ZipFile(BytesIO(workbook_bytes)) as workbook:
        shared = xlsx_shared_strings(workbook)
        catalog = ET.fromstring(workbook.read("xl/workbook.xml"))
        rels = ET.fromstring(workbook.read("xl/_rels/workbook.xml.rels"))
        target_by_id = {rel.attrib["Id"]: rel.attrib["Target"] for rel in rels}
        sheet_path = None
        for sheet in catalog.findall(".//a:sheets/a:sheet", namespace):
            if sheet.attrib.get("name", "").strip().lower() == "4. nominal spot curve":
                target = target_by_id[sheet.attrib[f"{rel_ns}id"]]
                sheet_path = "xl/" + target.lstrip("/").replace("../", "")
                break
        if sheet_path is None:
            return {}
        sheet = ET.fromstring(workbook.read(sheet_path))

    def cell_value(cell) -> str:
        raw = cell.find("a:v", namespace)
        if raw is None:
            return ""
        if cell.attrib.get("t") == "s":
            return shared[int(raw.text or "0")]
        return raw.text or ""

    rows = sheet.findall(".//a:sheetData/a:row", namespace)
    maturity_by_column: dict[int, float] = {}
    started = False
    yields: dict[str, float] = {}
    for row in rows:
        cells = {xlsx_column_index(c.attrib["r"]): c for c in row.findall("a:c", namespace)}
        first = cell_value(cells[0]) if 0 in cells else ""
        if not started:
            if first.strip() == "years:":
                for column, cell in cells.items():
                    try:
                        maturity_by_column[column] = float(cell_value(cell))
                    except ValueError:
                        continue
                ten_year_column = min(maturity_by_column, key=lambda col: abs(maturity_by_column[col] - 10.0))
                started = True
            continue
        if 0 not in cells or ten_year_column not in cells:
            continue
        try:
            serial = int(round(float(cell_value(cells[0]))))
            value = float(cell_value(cells[ten_year_column]))
        except ValueError:
            continue
        iso = (EXCEL_EPOCH + timedelta(days=serial)).isoformat()
        yields[iso] = value / 100.0
    return yields


def read_extracted_yields(path: Path) -> dict[str, float]:
    yields: dict[str, float] = {}
    with path.open(newline="", encoding="utf-8") as handle:
        for row in csv.DictReader(handle):
            value = row.get("spot_10y_pct", "").strip()
            if value:
                yields[row["Date"]] = float(value) / 100.0
    return yields


def fetch_boe_gilt_10y(raw_dir: Path, refresh_static_sources: bool = False) -> dict[str, float]:
    """Daily 10y nominal spot gilt yields (decimal) from the BoE GLC archive (1979+).

    The source is a ~39 MB zip of yearly Excel workbooks; only the compact extracted 10y
    series is persisted to sources/raw (the bulk archive is not committed).
    """
    extract_path = raw_dir / f"{ASSET_ID}_boe_gilt_10y.csv"
    if extract_path.exists() and not refresh_static_sources:
        log(f"Using cached BoE 10y gilt extract: {extract_path}")
        return read_extracted_yields(extract_path)

    log("Fetching BoE GLC archive for 10y gilt yields ...")
    archive_bytes = fetch_binary(BOE_GLC_URL)
    yields: dict[str, float] = {}
    with ZipFile(BytesIO(archive_bytes)) as archive:
        names = [name for name in archive.namelist() if name.lower().endswith(".xlsx")]
        for index, name in enumerate(names, start=1):
            if index == 1 or index % 10 == 0 or index == len(names):
                log(f"  Parsing BoE workbook {index}/{len(names)}")
            yields.update(parse_boe_workbook_10y(archive.read(name)))
    with extract_path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.writer(handle)
        writer.writerow(["Date", "spot_10y_pct"])
        for iso in sorted(yields):
            writer.writerow([iso, f"{yields[iso] * 100:.6f}"])
    return yields


def load_itt_daily_total_returns(path: Path) -> dict[str, Decimal]:
    """In-repo daily 7-10y U.S. Treasury total returns (the US bond leg, 1970+)."""
    if not path.exists():
        raise RuntimeError(f"Intermediate Treasury base dataset not found: {path}")
    returns: dict[str, Decimal] = {}
    with path.open(newline="", encoding="utf-8") as handle:
        for row in csv.DictReader(handle):
            total = row.get("Total Return", "").strip()
            if total:
                returns[row["Date"]] = Decimal(total)
    return returns


def _exchange_tz(meta: dict):
    timezone_name = meta.get("exchangeTimezoneName", "America/New_York")
    try:
        return ZoneInfo(timezone_name)
    except ZoneInfoNotFoundError:
        return timezone(timedelta(seconds=int(meta.get("gmtoffset", 0))))


def close_series(payload: dict, field: str = "adjclose") -> dict[str, float]:
    result = payload["chart"]["result"][0]
    timestamps = result.get("timestamp") or []
    quote = result["indicators"]["quote"][0]
    adjclose = result.get("indicators", {}).get("adjclose", [{}])[0].get("adjclose", [])
    exchange_tz = _exchange_tz(result.get("meta", {}))

    values: dict[str, float] = {}
    for index, timestamp in enumerate(timestamps):
        if field == "adjclose":
            value = adjclose[index] if index < len(adjclose) else None
        else:
            value = quote.get(field, [None])[index]
        if value is None:
            continue
        values[datetime.fromtimestamp(timestamp, exchange_tz).date().isoformat()] = float(value)
    return values


def xlsx_shared_strings(workbook: ZipFile) -> list[str]:
    if "xl/sharedStrings.xml" not in workbook.namelist():
        return []
    root = ET.fromstring(workbook.read("xl/sharedStrings.xml"))
    namespace = {"a": "http://schemas.openxmlformats.org/spreadsheetml/2006/main"}
    return ["".join((text.text or "") for text in item.findall(".//a:t", namespace))
            for item in root.findall("a:si", namespace)]


def xlsx_column_index(cell_ref: str) -> int:
    column = "".join(character for character in cell_ref if character.isalpha())
    result = 0
    for character in column:
        result = result * 26 + ord(character.upper()) - ord("A") + 1
    return result - 1


def xlsx_rows(workbook_bytes: bytes) -> list[list[str]]:
    namespace = {"a": "http://schemas.openxmlformats.org/spreadsheetml/2006/main"}
    with ZipFile(BytesIO(workbook_bytes)) as workbook:
        shared_strings = xlsx_shared_strings(workbook)
        root = ET.fromstring(workbook.read("xl/worksheets/sheet1.xml"))
        rows: list[list[str]] = []
        for row in root.findall(".//a:sheetData/a:row", namespace):
            values: list[str] = []
            for cell in row.findall("a:c", namespace):
                index = xlsx_column_index(cell.attrib["r"])
                while len(values) <= index:
                    values.append("")
                raw_value = cell.find("a:v", namespace)
                if raw_value is None:
                    values[index] = ""
                elif cell.attrib.get("t") == "s":
                    values[index] = shared_strings[int(raw_value.text or "0")]
                else:
                    values[index] = raw_value.text or ""
            rows.append(values)
    return rows


def _decimal_or_none(value: str) -> Decimal | None:
    value = (value or "").strip()
    if not value:
        return None
    return Decimal(value)


def parse_jst_rows(workbook_bytes: bytes) -> list[dict[str, str]]:
    rows = xlsx_rows(workbook_bytes)
    header = rows[0]
    return [{header[index]: value for index, value in enumerate(row) if index < len(header)} for row in rows[1:]]


def jst_basket(records: list[dict[str, str]]) -> tuple[dict[int, Decimal], dict[int, dict[str, Decimal]]]:
    """Annual GDP-weighted unhedged USD government-bond basket return and country weights.

    Returns (annual_returns, weights_by_year) where weights_by_year[year][iso] is the
    prior-year real-GDP weight used for that year's basket (sums to 1 across countries).

    Weights use comparable real GDP (`rgdpmad` real GDP per capita in 1990 international
    dollars x `pop` population) rather than JST's nominal `gdp` column. JST `gdp` is in
    local-currency units that are inconsistent across countries (e.g. the U.S. figure is in
    billions of USD while Spain's is in millions of pesetas), so `gdp / xrusd` does not
    yield comparable cross-country GDP and badly mis-weights the basket toward small
    economies. Real GDP in common international dollars is comparable across all countries.
    """
    by_country_year: dict[tuple[str, int], dict[str, Decimal]] = {}
    for row in records:
        raw_year = row.get("year", "")
        iso = row.get("iso", "")
        if not raw_year or not iso:
            continue
        year = int(Decimal(raw_year))
        bond_tr = _decimal_or_none(row.get("bond_tr", ""))
        xrusd = _decimal_or_none(row.get("xrusd", ""))
        rgdp_per_capita = _decimal_or_none(row.get("rgdpmad", ""))
        population = _decimal_or_none(row.get("pop", ""))
        if bond_tr is None or xrusd is None or xrusd <= 0:
            continue
        if rgdp_per_capita is None or population is None or rgdp_per_capita <= 0 or population <= 0:
            continue
        by_country_year[(iso, year)] = {
            "bond_tr": bond_tr,
            "xrusd": xrusd,
            "real_gdp": rgdp_per_capita * population,
        }

    annual: dict[int, Decimal] = {}
    weights: dict[int, dict[str, Decimal]] = {}
    for year in range(START_DATE.year, ETF_BLEND_START.year + 1):
        contributions: list[tuple[str, Decimal, Decimal]] = []  # iso, prev_real_gdp, usd_return
        for (iso, record_year), current in by_country_year.items():
            if record_year != year:
                continue
            previous = by_country_year.get((iso, year - 1))
            if previous is None:
                continue
            # xrusd is local currency per USD. A local asset converted to USD gains from local
            # currency appreciation by multiplying by previous_xrusd/current_xrusd.
            usd_return = (Decimal("1") + current["bond_tr"]) * (previous["xrusd"] / current["xrusd"]) - Decimal("1")
            contributions.append((iso, previous["real_gdp"], usd_return))
        total_weight = sum(weight for _, weight, _ in contributions)
        if total_weight <= 0:
            continue
        annual[year] = sum(weight / total_weight * ret for _, weight, ret in contributions)
        weights[year] = {iso: weight / total_weight for iso, weight, _ in contributions}
    return annual, weights


def jst_annual_unhedged_returns(records: list[dict[str, str]]) -> dict[int, Decimal]:
    """Backwards-compatible accessor returning only the annual basket returns."""
    return jst_basket(records)[0]


def load_base_dates(base_csv: Path, end_date: date) -> list[str]:
    if not base_csv.exists():
        raise RuntimeError(f"Base calendar dataset not found: {base_csv}")
    dates: list[str] = []
    with base_csv.open(newline="", encoding="utf-8") as handle:
        for row in csv.DictReader(handle):
            if START_DATE.isoformat() <= row["Date"] <= end_date.isoformat():
                dates.append(row["Date"])
    return dates


def price_flat_par_bond(coupon_rate: float, yield_rate: float, maturity_years: float) -> float:
    """Price (per 100 face) of a semiannual-coupon bond at a flat yield.

    With coupon_rate == yield_rate the price is exactly par (100), so a par bond struck at
    last month's yield and repriced at this month's yield gives the constant-maturity price
    move from the yield change.
    """
    periods = max(1, int(round(maturity_years * 2)))
    coupon = coupon_rate / 2.0 * 100.0
    semi_yield = yield_rate / 2.0
    price = 0.0
    for period in range(1, periods + 1):
        cashflow = coupon + (100.0 if period == periods else 0.0)
        price += cashflow / (1.0 + semi_yield) ** period
    return price


def _previous_month(month_key: str) -> str:
    year, month = (int(part) for part in month_key.split("-"))
    if month == 1:
        return f"{year - 1}-12"
    return f"{year}-{month - 1:02d}"


def monthly_bond_returns(yields: dict[str, dict[str, float]]) -> dict[str, dict[str, Decimal]]:
    """Per-country monthly 10y constant-maturity total return (price move + coupon carry)."""
    result: dict[str, dict[str, Decimal]] = {}
    for iso, series in yields.items():
        country: dict[str, Decimal] = {}
        for month_key, current_yield in series.items():
            previous_key = _previous_month(month_key)
            previous_yield = series.get(previous_key)
            if previous_yield is None:
                continue
            # Constant-maturity 10y par bond: par at last month's yield, repriced at this
            # month's yield, plus one month of coupon carry.
            price = price_flat_par_bond(previous_yield, current_yield, BOND_MATURITY_YEARS)
            carry = previous_yield * 100.0 / 12.0
            country[month_key] = Decimal(str((price + carry) / 100.0 - 1.0))
        result[iso] = country
    return result


def daily_bond_returns_from_yields(yields: dict[str, float], grid: list[str]) -> dict[str, Decimal]:
    """Genuine daily 10y constant-maturity total return from daily yields on the grid.

    Yields are forward-filled onto the trading grid; between consecutive grid days the bond
    is repriced (par bond struck at the previous yield, repriced at the current yield) and
    actual-day coupon carry is added. Days where the national market did not move carry only.
    """
    filled = forward_fill_levels(yields, grid)
    result: dict[str, Decimal] = {}
    previous_day: str | None = None
    previous_yield: float | None = None
    for day in grid:
        current_yield = filled.get(day)
        if current_yield is not None and previous_yield is not None and previous_day is not None:
            elapsed_days = (date.fromisoformat(day) - date.fromisoformat(previous_day)).days
            price = price_flat_par_bond(previous_yield, current_yield, BOND_MATURITY_YEARS)
            carry = previous_yield * 100.0 * (elapsed_days / 365.25)
            result[day] = Decimal(str((price + carry) / 100.0 - 1.0))
        if current_yield is not None:
            previous_day = day
            previous_yield = current_yield
    return result


def forward_fill_levels(levels: dict[str, float], grid: list[str]) -> dict[str, float]:
    """Carry the most recent observed level forward onto each grid date."""
    items = sorted(levels.items())
    out: dict[str, float] = {}
    index = 0
    last: float | None = None
    for day in grid:
        while index < len(items) and items[index][0] <= day:
            last = items[index][1]
            index += 1
        if last is not None:
            out[day] = last
    return out


def build_early_daily_returns(
    early_grid: list[str],
    weights_by_year: dict[int, dict[str, Decimal]],
    fx_levels: dict[str, dict[str, float]],
    yields: dict[str, dict[str, float]],
    annual_returns: dict[int, Decimal],
    daily_bond_override: dict[str, dict[str, Decimal]] | None = None,
) -> dict[str, Decimal]:
    """Daily basket returns for 1970..ETF blend, anchored so each year matches JST.

    `daily_bond_override[iso][date]` supplies a genuine daily bond total return for a country
    on a given day (US/JP/UK); where absent, the within-month-smoothed OECD monthly bond
    return is used instead.
    """
    if not early_grid:
        return {}
    daily_bond_override = daily_bond_override or {}

    monthly_bonds = monthly_bond_returns(yields)

    # Genuine daily FX returns per country on the trading grid (USA == 0).
    fx_returns: dict[str, dict[str, Decimal]] = {}
    for iso in COUNTRIES:
        if COUNTRY_FX[iso] is None:
            continue
        grid_levels = forward_fill_levels(fx_levels.get(iso, {}), early_grid)
        country: dict[str, Decimal] = {}
        previous: float | None = None
        for day in early_grid:
            level = grid_levels.get(day)
            if level is not None and previous is not None and previous > 0:
                # Local currency per USD: USD return is previous / current.
                country[day] = Decimal(str(previous)) / Decimal(str(level)) - Decimal("1")
            if level is not None:
                previous = level
        fx_returns[iso] = country

    # Group grid days by calendar month and pre-compute the GDP-weighted basket monthly
    # bond return so countries without an observed yield that month fall back to the basket.
    days_by_month: dict[str, list[str]] = {}
    for day in early_grid:
        days_by_month.setdefault(day[:7], []).append(day)

    basket_monthly: dict[str, Decimal] = {}
    for month_key, days in days_by_month.items():
        year = int(month_key[:4])
        weights = weights_by_year.get(year, {})
        weighted_sum = Decimal("0")
        weight_total = Decimal("0")
        for iso in COUNTRIES:
            value = monthly_bonds.get(iso, {}).get(month_key)
            if value is None:
                continue
            weight = weights.get(iso, Decimal("0"))
            if weight <= 0:
                continue
            weighted_sum += weight * value
            weight_total += weight
        basket_monthly[month_key] = weighted_sum / weight_total if weight_total > 0 else Decimal("0")

    # Combine per-country (daily FX) x (within-month-smoothed bond), GDP-weight into a basket.
    raw_daily: dict[str, Decimal] = {}
    for month_key, days in days_by_month.items():
        year = int(month_key[:4])
        weights = weights_by_year.get(year, {})
        if not weights:
            continue
        count = len(days)
        fallback = basket_monthly.get(month_key, Decimal("0"))
        # Per-country within-month daily bond factor.
        daily_bond: dict[str, Decimal] = {}
        for iso in COUNTRIES:
            monthly = monthly_bonds.get(iso, {}).get(month_key, fallback)
            daily_bond[iso] = Decimal(str(math.pow(1.0 + float(monthly), 1.0 / count))) - Decimal("1")
        for day in days:
            basket = Decimal("0")
            for iso in COUNTRIES:
                weight = weights.get(iso)
                if weight is None:
                    continue
                fx = fx_returns.get(iso, {}).get(day, Decimal("0"))
                bond = daily_bond_override.get(iso, {}).get(day)
                if bond is None:
                    bond = daily_bond[iso]
                country_return = (Decimal("1") + bond) * (Decimal("1") + fx) - Decimal("1")
                basket += weight * country_return
            raw_daily[day] = basket

    # Per-year multiplicative overlay so each calendar year compounds exactly to the JST
    # annual basket return (the first grid day carries no return, mirroring GLSTOCK).
    overlaid: dict[str, Decimal] = {}
    days_by_year: dict[int, list[str]] = {}
    for day in early_grid:
        days_by_year.setdefault(int(day[:4]), []).append(day)

    first_day = early_grid[0]
    for year, days in days_by_year.items():
        return_days = [day for day in days if day != first_day]
        if not return_days or year not in annual_returns:
            continue
        growth = Decimal("1")
        for day in return_days:
            growth *= Decimal("1") + raw_daily.get(day, Decimal("0"))
        target_growth = Decimal("1") + annual_returns[year]
        overlay_log = (target_growth.ln() - growth.ln()) / Decimal(len(return_days))
        overlay_factor = Decimal(str(math.exp(float(overlay_log))))
        for day in return_days:
            overlaid[day] = (Decimal("1") + raw_daily.get(day, Decimal("0"))) * overlay_factor - Decimal("1")
    return overlaid


def raw_return(series: dict[str, float], previous_value: float | None, current: str) -> Decimal | None:
    value = series.get(current)
    if value is None or previous_value is None:
        return None
    return Decimal(str(value)) / Decimal(str(previous_value)) - Decimal("1")


def round_decimal(value: Decimal) -> str:
    return f"{value:.10f}".rstrip("0").rstrip(".")


def build_rows(
    base_dates: list[str],
    annual_returns: dict[int, Decimal],
    weights_by_year: dict[int, dict[str, Decimal]],
    fx_levels: dict[str, dict[str, float]],
    yields: dict[str, dict[str, float]],
    daily_bond_sources: dict[str, dict[str, Decimal]],
    bnd_adj: dict[str, float],
    bwx_adj: dict[str, float],
    end_date: date,
) -> tuple[list[dict[str, str]], dict]:
    blend_start = max(min(bnd_adj), min(bwx_adj))
    all_dates = sorted(set(base_dates) | {d for d in bnd_adj if d <= end_date.isoformat()} | {d for d in bwx_adj if d <= end_date.isoformat()})

    early_grid = [d for d in base_dates if d < blend_start and START_DATE.isoformat() <= d <= end_date.isoformat()]
    early_grid_set = set(early_grid)
    daily_bond_override = {
        iso: {day: ret for day, ret in series.items() if day in early_grid_set}
        for iso, series in daily_bond_sources.items()
    }
    early_daily = build_early_daily_returns(
        early_grid, weights_by_year, fx_levels, yields, annual_returns, daily_bond_override
    )

    rows: list[dict[str, str]] = []
    level = Decimal("100")
    prev_bnd: float | None = None
    prev_bwx: float | None = None
    counts: dict[str, int] = {}

    for current in all_dates:
        if current < START_DATE.isoformat() or current > end_date.isoformat():
            continue
        if not rows:
            rows.append(row_for(current, level, "", EARLY_FLAG, EARLY_SOURCE, EARLY_NOTES))
            counts[EARLY_FLAG] = counts.get(EARLY_FLAG, 0) + 1
        else:
            daily_return: Decimal | None
            if current > blend_start:
                bnd_ret = raw_return(bnd_adj, prev_bnd, current)
                bwx_ret = raw_return(bwx_adj, prev_bwx, current)
                if bnd_ret is None or bwx_ret is None:
                    daily_return = None
                else:
                    daily_return = BND_WEIGHT * bnd_ret + BWX_WEIGHT * bwx_ret
                flag, source, notes = ETF_BLEND_FLAG, ETF_BLEND_SOURCE, ETF_BLEND_NOTES
            else:
                daily_return = early_daily.get(current)
                flag, source, notes = EARLY_FLAG, EARLY_SOURCE, EARLY_NOTES
            if daily_return is not None:
                level *= Decimal("1") + daily_return
                rows.append(row_for(current, level, daily_return, flag, source, notes))
                counts[flag] = counts.get(flag, 0) + 1

        if current in bnd_adj:
            prev_bnd = bnd_adj[current]
        if current in bwx_adj:
            prev_bwx = bwx_adj[current]

    daily_rate_coverage = {
        iso: {
            "first": min(series),
            "last": max(series),
            "count": len(series),
        }
        for iso, series in daily_bond_override.items()
        if series
    }

    return rows, {
        "blend_start": blend_start,
        "segment_counts": counts,
        "jst_annual_years": [min(annual_returns), max(annual_returns)],
        "early_countries": COUNTRIES,
        "bond_maturity_years": BOND_MATURITY_YEARS,
        "daily_rate_countries": list(DAILY_RATE_COUNTRIES),
        "daily_rate_coverage": daily_rate_coverage,
        "bnd_weight": str(BND_WEIGHT),
        "bwx_weight": str(BWX_WEIGHT),
    }


def row_for(day: str, level: Decimal, daily_return: Decimal | str, flag: str, source: str, notes: str) -> dict[str, str]:
    ret = "" if daily_return == "" else round_decimal(daily_return)  # type: ignore[arg-type]
    return {
        "Date": day,
        "Open": "",
        "High": "",
        "Low": "",
        "Close": round_decimal(level),
        "Adj Close": round_decimal(level),
        "Volume": "",
        "Price Return": ret,
        "Total Return": ret,
        "Source": source,
        "Quality Flag": flag,
        "Source Notes": notes,
    }


def write_csv(path: Path, rows: list[dict[str, str]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=OUTPUT_COLUMNS)
        writer.writeheader()
        writer.writerows(rows)


def write_parquet_if_available(csv_path: Path, parquet_path: Path) -> bool:
    try:
        import pandas as pd
    except ImportError:
        return False
    try:
        frame = pd.read_csv(csv_path, parse_dates=["Date"])
        frame.to_parquet(parquet_path, index=False)
    except (ImportError, ModuleNotFoundError):
        return False
    return True


def checksum(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def write_build_metadata(path: Path, rows: list[dict[str, str]], csv_path: Path, parquet_written: bool, extra: dict) -> None:
    metadata = {
        "asset_id": ASSET_ID,
        "asset_name": ASSET_NAME,
        "alias": ALIAS,
        "build_timestamp_utc": datetime.now(timezone.utc).isoformat(),
        "row_count": len(rows),
        "first_date": rows[0]["Date"] if rows else None,
        "last_date": rows[-1]["Date"] if rows else None,
        "csv_path": csv_path.relative_to(path.parent.parent.parent).as_posix(),
        "csv_sha256": checksum(csv_path),
        "parquet_written": parquet_written,
        "quality_flags": sorted({row["Quality Flag"] for row in rows}),
        **extra,
    }
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(metadata, indent=2) + "\n", encoding="utf-8")


def main() -> None:
    args = parse_args()
    root = Path(args.root)
    end_date = date.fromisoformat(args.end_date)
    raw_dir = root / "sources" / "raw"
    raw_dir.mkdir(parents=True, exist_ok=True)

    refresh_static = args.refresh_static_sources
    jst_bytes = cached_binary(raw_dir, f"{ASSET_ID}_jst_macrohistory_r6.xlsx", JST_URL, refresh_static, "JST Macrohistory workbook")
    fx_levels = fetch_bis_fx(raw_dir, refresh_static)
    yields = fetch_oecd_yields(raw_dir, refresh_static)
    jgb_yields = fetch_mof_jgb_10y(raw_dir, refresh_static)
    gilt_yields = fetch_boe_gilt_10y(raw_dir, refresh_static)
    log(f"Fetching {BND_SYMBOL} ...")
    bnd_payload = fetch_chart(BND_SYMBOL, end_date)
    log(f"Fetching {BWX_SYMBOL} ...")
    bwx_payload = fetch_chart(BWX_SYMBOL, end_date)
    (raw_dir / f"{ASSET_ID}_yahoo_bnd_chart.json").write_text(json.dumps(bnd_payload), encoding="utf-8")
    (raw_dir / f"{ASSET_ID}_yahoo_bwx_chart.json").write_text(json.dumps(bwx_payload), encoding="utf-8")

    log("Building GLBOND rows ...")
    annual_returns, weights_by_year = jst_basket(parse_jst_rows(jst_bytes))
    base_dates = load_base_dates(root / "data" / "processed" / "us_large_cap_sp500.csv", end_date)
    itt_returns = load_itt_daily_total_returns(root / "data" / "processed" / ITT_CSV_NAME)
    daily_bond_sources = {
        "USA": itt_returns,
        "JPN": daily_bond_returns_from_yields(jgb_yields, base_dates),
        "GBR": daily_bond_returns_from_yields(gilt_yields, base_dates),
    }
    rows, extra = build_rows(
        base_dates, annual_returns, weights_by_year, fx_levels, yields, daily_bond_sources,
        close_series(bnd_payload), close_series(bwx_payload), end_date,
    )
    if not rows:
        raise RuntimeError("No global bond rows were built")

    interim_csv = root / "data" / "interim" / f"{ASSET_ID}.csv"
    processed_csv = root / "data" / "processed" / f"{ASSET_ID}.csv"
    processed_parquet = root / "data" / "processed" / f"{ASSET_ID}.parquet"
    write_csv(interim_csv, rows)
    write_csv(processed_csv, rows)
    parquet_written = write_parquet_if_available(processed_csv, processed_parquet)
    write_build_metadata(root / "sources" / "manifests" / f"{ASSET_ID}_build.json", rows, processed_csv, parquet_written, extra)

    print(f"Wrote {len(rows)} rows to {processed_csv}")
    print(f"Date range: {rows[0]['Date']} to {rows[-1]['Date']}")
    print(f"Segments: {extra['segment_counts']}")
    print(f"Daily rate coverage: {extra['daily_rate_coverage']}")
    if parquet_written:
        print(f"Wrote Parquet to {processed_parquet}")
    else:
        print("Parquet not written because pandas/pyarrow is unavailable")


if __name__ == "__main__":
    main()
