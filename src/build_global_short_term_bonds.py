"""Build an unhedged global SHORT-TERM (1-3yr) sovereign bond total-return proxy dataset.

ISHG-like in maturity but global in scope (includes the US). The 1970-2009 segment is a
*direct* daily total-return reconstruction (no JST annual overlay): a GDP-weighted basket
across 16 advanced economies of observed daily FX (BIS) and a constant-maturity 2-year par
bond repriced from short-end yields plus coupon carry. The 2-year yield is genuinely daily
for the US (in-repo 2yr Treasury TR, 1970+), Japan (MoF 2yr JGB, 1974-09+) and the UK (BoE
2yr nominal spot, 1979+); for the rest, and earlier years, a monthly 2-year yield is
interpolated between the OECD MEI 3-month and 10-year rates, with the JST annual short/long
rates as the pre-OECD fallback. From the ISHG/BWZ inception (2009) onward the dataset uses
an observed GDP-weighted, annually-rebalanced blend of SHY (US short Treasuries) and the
ISHG+BWZ average (developed ex-US short Treasuries, unhedged).

Modeled fees: `Close` (= Price Return) is the GROSS-of-fee total return; `Adj Close` (=
Total Return) is NET of a representative ~0.26%/yr fund expense drag. In the model era the
fee is subtracted from the gross basket; in the observed era the ETF returns are already
net (Yahoo adjusted close), so the fee is added back to keep `Close` gross. Backtesters
that read `Adj Close` / `Total Return` therefore get an investable, net-of-fee series.
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

ASSET_ID = "global_short_term_bonds"
ASSET_NAME = "Unhedged Global Short-Term (1-3yr) Government Bonds Total-Return Proxy"
ALIAS = "GLSTBOND"

START_DATE = date(1970, 1, 1)
# Observed era begins on the first common ISHG/BWZ trading day (BWZ inception 2009-01-30).
ETF_BLEND_START = date(2009, 1, 30)
JST_URL = "https://www.macrohistory.net/app/download/9834512569/JSTdatasetR6.xlsx?t=1720600177"
# Observed segment: US short Treasuries (SHY) + developed ex-US short Treasuries (ISHG/BWZ
# averaged). The US-vs-ex-US split is GDP-weighted and annually rebalanced, not fixed.
SHY_SYMBOL = "SHY"
ISHG_SYMBOL = "ISHG"
BWZ_SYMBOL = "BWZ"

# Representative all-in fund expense drag for a global short government bond holding,
# blended from SHY (~0.15%/yr) and ISHG/BWZ (~0.35%/yr) at roughly GDP weights.
REPRESENTATIVE_FEE_ANNUAL = Decimal("0.0026")

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
BOND_MATURITY_YEARS = 2.0  # Constant-maturity 2-year par bond (mid-point of the 1-3yr band).

# Maturities (years) used to interpolate a 2-year yield from the OECD MEI short and long
# rates: 3-month interbank (~0.25y) and the 10-year long-term government bond (~10y).
SHORT_RATE_MATURITY_YEARS = 0.25
LONG_RATE_MATURITY_YEARS = 10.0

# Genuine daily bond-return sources for the three largest weights (others stay monthly):
#   USA -> in-repo daily 2yr Treasury total return (Fed yield-curve model -> SHY).
#   JPN -> MoF daily 2yr JGB yield (continuous from 1974-09).
#   GBR -> BoE GLC daily 2yr nominal spot yield (from 1979).
STT_CSV_NAME = "short_term_us_treasury.csv"
MOF_JGB_URL = "https://www.mof.go.jp/jgbs/reference/interest_rate/data/jgbcm_all.csv"
BOE_GLC_URL = "https://www.bankofengland.co.uk/-/media/boe/files/statistics/yield-curves/glcnominalddata.zip"
DAILY_RATE_COUNTRIES = ("USA", "JPN", "GBR")
EXCEL_EPOCH = date(1899, 12, 30)

YAHOO_COLUMNS = ["Date", "Open", "High", "Low", "Close", "Adj Close", "Volume"]
PROJECT_COLUMNS = ["Price Return", "Total Return", "Source", "Quality Flag", "Source Notes"]
OUTPUT_COLUMNS = YAHOO_COLUMNS + PROJECT_COLUMNS

EARLY_FLAG = "model_direct_daily_fx_2y_yield_global_short_govt_bond_unhedged_net_of_fee"
ETF_BLEND_FLAG = "observed_shy_ishg_bwz_gdp_weighted_short_govt_bond_unhedged_net_of_fee"

EARLY_SOURCE = "BIS daily FX + daily 2yr US/JP/UK + OECD MEI monthly 2yr-interpolated yields"
ETF_BLEND_SOURCE = "Yahoo Finance chart API (SHY + ISHG/BWZ adjusted-close total returns)"

EARLY_NOTES = (
    "Unhedged USD global SHORT-TERM (1-3yr) government-bond model. Daily path = GDP-weighted "
    "basket of observed daily FX returns (BIS, local currency per USD) and a constant-"
    "maturity 2yr par-bond total return (reprice + coupon carry). The 2yr yield is daily for "
    "the US (in-repo 2yr Treasury TR, 1970+), Japan (MoF 2yr JGB, 1974-09+) and the UK (BoE "
    "2yr nominal spot, 1979+); other countries and earlier years interpolate a monthly 2yr "
    "yield between the OECD MEI 3-month and 10-year rates (JST annual short/long rates as the "
    "pre-OECD fallback). Built directly (no annual overlay). Close is gross; Adj Close/Total "
    "Return are net of a representative ~0.26%/yr fund expense drag."
)
ETF_BLEND_NOTES = (
    "Daily passive unhedged proxy: SHY US short Treasuries + the ISHG/BWZ average (developed "
    "ex-US short Treasuries in local currencies), GDP-weighted between US and ex-US and "
    "annually rebalanced, from adjusted-close (net-of-fee) returns. Close adds the fee back "
    "to remain gross."
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


def fetch_oecd_series(raw_dir: Path, mei_code: str, label: str, refresh_static_sources: bool = False) -> dict[str, dict[str, float]]:
    """Monthly OECD MEI rate (decimal) per country, by MEI measure code, via DBnomics."""
    cache_path = raw_dir / f"{ASSET_ID}_oecd_{label}.json"
    if cache_path.exists() and not refresh_static_sources:
        log(f"Using cached OECD {label}: {cache_path}")
        raw = json.loads(cache_path.read_text(encoding="utf-8"))
        return {iso: {period: value / 100.0 for period, value in dbnomics_observations(payload).items()}
                for iso, payload in raw.items()}

    log(f"Fetching OECD {label} via DBnomics ...")
    raw: dict[str, dict] = {}
    rates: dict[str, dict[str, float]] = {}
    for iso in COUNTRIES:
        series_code = f"{iso}.{mei_code}.ST.M"
        log(f"  OECD {iso} {series_code}")
        payload = fetch_dbnomics("OECD", "MEI", series_code)
        raw[iso] = payload
        # OECD MEI rates are in percent per annum; convert to decimal.
        rates[iso] = {period: value / 100.0 for period, value in dbnomics_observations(payload).items()}
    cache_path.write_text(json.dumps(raw), encoding="utf-8")
    return rates


def _interpolate_two_year(short_rate: float | None, long_rate: float | None) -> float | None:
    """Linear-in-maturity 2yr yield from a 3-month and a 10-year rate.

    Falls back to whichever single rate is available (the 2yr point is closer to the short
    rate, so a short-only fallback is conservative; a long-only fallback slightly overstates
    short-bond yield but is acceptable where no short rate exists).
    """
    if short_rate is None and long_rate is None:
        return None
    if short_rate is None:
        return long_rate
    if long_rate is None:
        return short_rate
    weight = (BOND_MATURITY_YEARS - SHORT_RATE_MATURITY_YEARS) / (
        LONG_RATE_MATURITY_YEARS - SHORT_RATE_MATURITY_YEARS
    )
    return short_rate + weight * (long_rate - short_rate)


def build_two_year_yields(
    oecd_short: dict[str, dict[str, float]],
    oecd_long: dict[str, dict[str, float]],
    jst_records: list[dict[str, str]],
) -> dict[str, dict[str, float]]:
    """Monthly 2-year yield (decimal) per country.

    Preferred source is OECD MEI (3-month + 10-year interpolated to 2yr). For months before
    a country's OECD coverage, the JST annual short (`stir`) and long (`ltrate`) rates
    (percent) are interpolated to 2yr and held across all twelve months of that year, so
    every country has a 2yr yield back to 1970.
    """
    # JST annual 2yr yield per country (percent -> decimal).
    jst_two_year: dict[str, dict[int, float]] = {iso: {} for iso in COUNTRIES}
    for row in jst_records:
        iso = row.get("iso", "")
        raw_year = row.get("year", "")
        if iso not in COUNTRIES or not raw_year:
            continue
        year = int(Decimal(raw_year))
        stir = _decimal_or_none(row.get("stir", ""))
        ltrate = _decimal_or_none(row.get("ltrate", ""))
        short = float(stir) / 100.0 if stir is not None else None
        long = float(ltrate) / 100.0 if ltrate is not None else None
        value = _interpolate_two_year(short, long)
        if value is not None:
            jst_two_year[iso][year] = value

    yields: dict[str, dict[str, float]] = {}
    for iso in COUNTRIES:
        months = sorted(set(oecd_short.get(iso, {})) | set(oecd_long.get(iso, {})))
        series: dict[str, float] = {}
        for month_key in months:
            value = _interpolate_two_year(
                oecd_short.get(iso, {}).get(month_key), oecd_long.get(iso, {}).get(month_key)
            )
            if value is not None:
                series[month_key] = value
        # Pre-OECD months: fill from the JST annual 2yr yield, but never overwrite OECD.
        oecd_start = min(series) if series else None
        for year, annual_value in jst_two_year[iso].items():
            for month in range(1, 13):
                month_key = f"{year:04d}-{month:02d}"
                if oecd_start is not None and month_key >= oecd_start:
                    continue
                series.setdefault(month_key, annual_value)
        yields[iso] = series
    return yields


def _japanese_era_to_iso(value: str) -> str | None:
    """Convert a JST CSV date like 'S49.9.24' / 'H1.1.4' / 'R3.4.1' to ISO."""
    match = re.match(r"\s*([SHR])(\d+)\.(\d+)\.(\d+)\s*$", value)
    if not match:
        return None
    base = {"S": 1925, "H": 1988, "R": 2018}[match.group(1)]
    year = base + int(match.group(2))
    return f"{year:04d}-{int(match.group(3)):02d}-{int(match.group(4)):02d}"


def parse_mof_jgb_2y(content: bytes) -> dict[str, float]:
    """Parse daily 2-year JGB yields (decimal) from the Japanese MoF historical CSV.

    The MoF file publishes the 1yr..9yr nodes from 1974-09 (the 10yr only starts 1986-07),
    so the 2yr column gives Japan a daily short-end rate leg twelve years earlier than the
    10yr used by the broad GLBOND build.
    """
    lines = [line for line in content.decode("cp932", errors="replace").splitlines() if line.strip()]
    header = lines[1].split(",")  # row 1 holds maturity labels (e.g. "2年"); row 0 is a title
    # The 2-year column's label starts with "2" followed by a non-digit (excludes 20/25 year).
    two_year_index = next(i for i, label in enumerate(header) if re.match(r"^2\D", label.strip()))
    yields: dict[str, float] = {}
    for line in lines[2:]:
        cells = line.split(",")
        iso = _japanese_era_to_iso(cells[0])
        if iso is None or len(cells) <= two_year_index:
            continue
        raw_value = cells[two_year_index].strip()
        if raw_value in ("", "-"):
            continue
        yields[iso] = float(raw_value) / 100.0
    return yields


def fetch_mof_jgb_2y(raw_dir: Path, refresh_static_sources: bool = False) -> dict[str, float]:
    """Daily 2-year JGB yields (decimal) from the Japanese MoF historical CSV (1974-09+)."""
    content = cached_binary(raw_dir, f"{ASSET_ID}_mof_jgb.csv", MOF_JGB_URL, refresh_static_sources, "MoF JGB yield CSV")
    return parse_mof_jgb_2y(content)


def parse_boe_workbook_2y(workbook_bytes: bytes) -> dict[str, float]:
    """Extract daily 2y nominal spot yields (decimal) from one BoE GLC workbook."""
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
                target_column = min(
                    maturity_by_column, key=lambda col: abs(maturity_by_column[col] - BOND_MATURITY_YEARS)
                )
                started = True
            continue
        if 0 not in cells or target_column not in cells:
            continue
        try:
            serial = int(round(float(cell_value(cells[0]))))
            value = float(cell_value(cells[target_column]))
        except ValueError:
            continue
        iso = (EXCEL_EPOCH + timedelta(days=serial)).isoformat()
        yields[iso] = value / 100.0
    return yields


def read_extracted_yields(path: Path) -> dict[str, float]:
    yields: dict[str, float] = {}
    with path.open(newline="", encoding="utf-8") as handle:
        for row in csv.DictReader(handle):
            value = row.get("spot_2y_pct", "").strip()
            if value:
                yields[row["Date"]] = float(value) / 100.0
    return yields


def fetch_boe_gilt_2y(raw_dir: Path, refresh_static_sources: bool = False) -> dict[str, float]:
    """Daily 2y nominal spot gilt yields (decimal) from the BoE GLC archive (1979+).

    The source is a ~39 MB zip of yearly Excel workbooks; only the compact extracted 2y
    series is persisted to sources/raw (the bulk archive is not committed).
    """
    extract_path = raw_dir / f"{ASSET_ID}_boe_gilt_2y.csv"
    if extract_path.exists() and not refresh_static_sources:
        log(f"Using cached BoE 2y gilt extract: {extract_path}")
        return read_extracted_yields(extract_path)

    log("Fetching BoE GLC archive for 2y gilt yields ...")
    archive_bytes = fetch_binary(BOE_GLC_URL)
    yields: dict[str, float] = {}
    with ZipFile(BytesIO(archive_bytes)) as archive:
        names = [name for name in archive.namelist() if name.lower().endswith(".xlsx")]
        for index, name in enumerate(names, start=1):
            if index == 1 or index % 10 == 0 or index == len(names):
                log(f"  Parsing BoE workbook {index}/{len(names)}")
            yields.update(parse_boe_workbook_2y(archive.read(name)))
    with extract_path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.writer(handle)
        writer.writerow(["Date", "spot_2y_pct"])
        for iso in sorted(yields):
            writer.writerow([iso, f"{yields[iso] * 100:.6f}"])
    return yields


def load_stt_daily_total_returns(path: Path) -> dict[str, Decimal]:
    """In-repo daily 1-3yr U.S. Treasury total returns (the US short bond leg, 1970+)."""
    if not path.exists():
        raise RuntimeError(f"Short-term Treasury base dataset not found: {path}")
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


def us_weight_by_year(records: list[dict[str, str]], through_year: int) -> dict[int, Decimal]:
    """US share of developed-market real GDP per year, carried forward past JST coverage.

    Used to GDP-weight the observed SHY (US) vs ISHG/BWZ (ex-US) blend, so the split evolves
    over time instead of being a fixed ratio. Real GDP (`rgdpmad` x `pop`, comparable 1990
    international dollars) is summed across the 16 countries each year; the US share is the US
    figure over that total. Years after the last JST observation reuse the last known share.
    """
    real_gdp: dict[int, dict[str, Decimal]] = {}
    for row in records:
        iso = row.get("iso", "")
        raw_year = row.get("year", "")
        if iso not in COUNTRIES or not raw_year:
            continue
        rgdp = _decimal_or_none(row.get("rgdpmad", ""))
        pop = _decimal_or_none(row.get("pop", ""))
        if rgdp is None or pop is None or rgdp <= 0 or pop <= 0:
            continue
        real_gdp.setdefault(int(Decimal(raw_year)), {})[iso] = rgdp * pop

    shares: dict[int, Decimal] = {}
    for year, by_iso in real_gdp.items():
        total = sum(by_iso.values())
        us = by_iso.get("USA")
        if total > 0 and us is not None:
            shares[year] = us / total

    if not shares:
        return {}
    filled: dict[int, Decimal] = {}
    last = shares[min(shares)]
    for year in range(min(shares), through_year + 1):
        if year in shares:
            last = shares[year]
        filled[year] = last
    return filled


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
    daily_bond_override: dict[str, dict[str, Decimal]] | None = None,
) -> dict[str, Decimal]:
    """Daily basket returns for 1970..ETF blend, built directly (no JST annual overlay).

    `daily_bond_override[iso][date]` supplies a genuine daily 2yr bond total return for a
    country on a given day (US/JP/UK); where absent, the within-month-smoothed monthly 2yr
    bond return is used instead. Unlike the broad GLBOND build there is no annual JST anchor:
    JST's long-bond return is the wrong level for a short-bond series, and short bonds are
    carry-dominated, so the daily path is compounded as-is.
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

    # Direct construction: the first grid day carries no return; every later day uses its
    # compounded basket return as-is (no annual rescaling).
    first_day = early_grid[0]
    return {day: ret for day, ret in raw_daily.items() if day != first_day}


def raw_return(series: dict[str, float], previous_value: float | None, current: str) -> Decimal | None:
    value = series.get(current)
    if value is None or previous_value is None:
        return None
    return Decimal(str(value)) / Decimal(str(previous_value)) - Decimal("1")


def round_decimal(value: Decimal) -> str:
    return f"{value:.10f}".rstrip("0").rstrip(".")


def _intl_return(
    ishg_adj: dict[str, float], bwz_adj: dict[str, float],
    prev_ishg: float | None, prev_bwz: float | None, current: str,
) -> Decimal | None:
    """Average of the available ISHG/BWZ daily returns (developed ex-US short Treasuries)."""
    legs = [r for r in (raw_return(ishg_adj, prev_ishg, current), raw_return(bwz_adj, prev_bwz, current)) if r is not None]
    if not legs:
        return None
    return sum(legs) / Decimal(len(legs))


def build_rows(
    base_dates: list[str],
    weights_by_year: dict[int, dict[str, Decimal]],
    us_weight: dict[int, Decimal],
    fx_levels: dict[str, dict[str, float]],
    yields: dict[str, dict[str, float]],
    daily_bond_sources: dict[str, dict[str, Decimal]],
    shy_adj: dict[str, float],
    ishg_adj: dict[str, float],
    bwz_adj: dict[str, float],
    end_date: date,
) -> tuple[list[dict[str, str]], dict]:
    blend_start = max(min(shy_adj), min(ishg_adj), min(bwz_adj))
    etf_dates = {d for series in (shy_adj, ishg_adj, bwz_adj) for d in series if d <= end_date.isoformat()}
    all_dates = sorted(set(base_dates) | etf_dates)

    early_grid = [d for d in base_dates if d < blend_start and START_DATE.isoformat() <= d <= end_date.isoformat()]
    early_grid_set = set(early_grid)
    daily_bond_override = {
        iso: {day: ret for day, ret in series.items() if day in early_grid_set}
        for iso, series in daily_bond_sources.items()
    }
    early_daily = build_early_daily_returns(
        early_grid, weights_by_year, fx_levels, yields, daily_bond_override
    )

    last_us_weight = us_weight[max(us_weight)] if us_weight else Decimal("0.45")

    rows: list[dict[str, str]] = []
    gross_level = Decimal("100")  # gross-of-fee total return -> Close / Price Return
    net_level = Decimal("100")    # net-of-fee total return   -> Adj Close / Total Return
    prev_shy: float | None = None
    prev_ishg: float | None = None
    prev_bwz: float | None = None
    prev_date: str | None = None
    counts: dict[str, int] = {}

    for current in all_dates:
        if current < START_DATE.isoformat() or current > end_date.isoformat():
            continue
        if not rows:
            rows.append(row_for(current, gross_level, net_level, "", "", EARLY_FLAG, EARLY_SOURCE, EARLY_NOTES))
            counts[EARLY_FLAG] = counts.get(EARLY_FLAG, 0) + 1
            prev_date = current
        else:
            gross_ret: Decimal | None
            net_ret: Decimal | None
            elapsed = (date.fromisoformat(current) - date.fromisoformat(prev_date)).days if prev_date else 1
            fee = REPRESENTATIVE_FEE_ANNUAL * Decimal(elapsed) / Decimal("365")
            if current > blend_start:
                shy_ret = raw_return(shy_adj, prev_shy, current)
                intl_ret = _intl_return(ishg_adj, bwz_adj, prev_ishg, prev_bwz, current)
                if shy_ret is None or intl_ret is None:
                    gross_ret = net_ret = None
                else:
                    weight = us_weight.get(int(current[:4]), last_us_weight)
                    # ETF adjusted-close returns are already net of fees.
                    net_ret = weight * shy_ret + (Decimal("1") - weight) * intl_ret
                    gross_ret = (Decimal("1") + net_ret) / (Decimal("1") - fee) - Decimal("1")
                flag, source, notes = ETF_BLEND_FLAG, ETF_BLEND_SOURCE, ETF_BLEND_NOTES
            else:
                gross_ret = early_daily.get(current)
                # Model basket is gross; subtract the modeled fund expense drag for the net leg.
                net_ret = None if gross_ret is None else (Decimal("1") + gross_ret) * (Decimal("1") - fee) - Decimal("1")
                flag, source, notes = EARLY_FLAG, EARLY_SOURCE, EARLY_NOTES
            if gross_ret is not None and net_ret is not None:
                gross_level *= Decimal("1") + gross_ret
                net_level *= Decimal("1") + net_ret
                rows.append(row_for(current, gross_level, net_level, gross_ret, net_ret, flag, source, notes))
                counts[flag] = counts.get(flag, 0) + 1
                prev_date = current

        if current in shy_adj:
            prev_shy = shy_adj[current]
        if current in ishg_adj:
            prev_ishg = ishg_adj[current]
        if current in bwz_adj:
            prev_bwz = bwz_adj[current]

    daily_rate_coverage = {
        iso: {"first": min(series), "last": max(series), "count": len(series)}
        for iso, series in daily_bond_override.items()
        if series
    }
    weight_years = sorted(us_weight)

    return rows, {
        "blend_start": blend_start,
        "segment_counts": counts,
        "early_countries": COUNTRIES,
        "bond_maturity_years": BOND_MATURITY_YEARS,
        "daily_rate_countries": list(DAILY_RATE_COUNTRIES),
        "daily_rate_coverage": daily_rate_coverage,
        "representative_fee_annual": str(REPRESENTATIVE_FEE_ANNUAL),
        "observed_symbols": [SHY_SYMBOL, ISHG_SYMBOL, BWZ_SYMBOL],
        "us_gdp_weight_first": {"year": weight_years[0], "weight": str(us_weight[weight_years[0]])} if weight_years else None,
        "us_gdp_weight_last": {"year": weight_years[-1], "weight": str(us_weight[weight_years[-1]])} if weight_years else None,
    }


def row_for(
    day: str, gross_level: Decimal, net_level: Decimal,
    gross_ret: Decimal | str, net_ret: Decimal | str,
    flag: str, source: str, notes: str,
) -> dict[str, str]:
    price = "" if gross_ret == "" else round_decimal(gross_ret)  # type: ignore[arg-type]
    total = "" if net_ret == "" else round_decimal(net_ret)  # type: ignore[arg-type]
    return {
        "Date": day,
        "Open": "",
        "High": "",
        "Low": "",
        "Close": round_decimal(gross_level),
        "Adj Close": round_decimal(net_level),
        "Volume": "",
        "Price Return": price,
        "Total Return": total,
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
    jst_records = parse_jst_rows(jst_bytes)
    fx_levels = fetch_bis_fx(raw_dir, refresh_static)
    oecd_short = fetch_oecd_series(raw_dir, "IR3TIB01", "short_3m", refresh_static)
    oecd_long = fetch_oecd_series(raw_dir, "IRLTLT01", "long_10y", refresh_static)
    yields = build_two_year_yields(oecd_short, oecd_long, jst_records)
    jgb_yields = fetch_mof_jgb_2y(raw_dir, refresh_static)
    gilt_yields = fetch_boe_gilt_2y(raw_dir, refresh_static)
    log(f"Fetching {SHY_SYMBOL} ...")
    shy_payload = fetch_chart(SHY_SYMBOL, end_date)
    log(f"Fetching {ISHG_SYMBOL} ...")
    ishg_payload = fetch_chart(ISHG_SYMBOL, end_date)
    log(f"Fetching {BWZ_SYMBOL} ...")
    bwz_payload = fetch_chart(BWZ_SYMBOL, end_date)
    for symbol, payload in (("shy", shy_payload), ("ishg", ishg_payload), ("bwz", bwz_payload)):
        (raw_dir / f"{ASSET_ID}_yahoo_{symbol}_chart.json").write_text(json.dumps(payload), encoding="utf-8")

    log("Building GLSTBOND rows ...")
    _, weights_by_year = jst_basket(jst_records)
    us_weight = us_weight_by_year(jst_records, end_date.year)
    base_dates = load_base_dates(root / "data" / "processed" / "us_large_cap_sp500.csv", end_date)
    stt_returns = load_stt_daily_total_returns(root / "data" / "processed" / STT_CSV_NAME)
    daily_bond_sources = {
        "USA": stt_returns,
        "JPN": daily_bond_returns_from_yields(jgb_yields, base_dates),
        "GBR": daily_bond_returns_from_yields(gilt_yields, base_dates),
    }
    rows, extra = build_rows(
        base_dates, weights_by_year, us_weight, fx_levels, yields, daily_bond_sources,
        close_series(shy_payload), close_series(ishg_payload), close_series(bwz_payload), end_date,
    )
    if not rows:
        raise RuntimeError("No global short-term bond rows were built")

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
