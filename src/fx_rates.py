"""Daily spot exchange rates against the U.S. dollar: AUD/USD, EUR/USD and GBP/USD.

Each dataset quotes U.S. dollars per one unit of the foreign currency, the usual
market convention for these three pairs. The source chain is:

* 1970-01-02 to 1998-12-31: BIS bilateral exchange rates (``WS_XRU``, local
  currency per USD), inverted. EUR uses the German series, which is the
  Deutsche Mark at the fixed 1.95583 conversion rate before the euro existed.
  BIS has no daily AUD observation before 1971-01-04, so the 1970 AUD rows are
  modeled from the observed daily sterling rate and the sterling peg.
* 1999-01-04 onward: ECB euro foreign exchange reference rates. EUR/USD is the
  published rate; AUD/USD and GBP/USD are crosses through the euro. BIS itself
  republishes these crosses, which the builder verifies on the 1999 overlap.

The ordinary daily update reads only the ECB file. BIS releases weekly, so it
cannot keep a daily dataset inside the publication gate's staleness limit.
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import io
import json
import statistics
import zipfile
from dataclasses import dataclass
from datetime import date, datetime, timedelta, timezone
from decimal import Decimal, getcontext
from pathlib import Path

import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry


getcontext().prec = 40
YAHOO_COLUMNS = ["Date", "Open", "High", "Low", "Close", "Adj Close", "Volume"]
OUTPUT_COLUMNS = YAHOO_COLUMNS + ["Price Return", "Total Return", "Source", "Quality Flag", "Source Notes"]
PROJECT_ROOT = Path(__file__).resolve().parents[1]

START_DATE = date(1970, 1, 2)
ECB_START = date(1999, 1, 4)  # First euro reference rate.
BIS_FETCH_START = date(1969, 12, 1)
BIS_FETCH_END = date(1999, 12, 31)  # One overlap year with ECB for the splice check.
BIS_URL = "https://stats.bis.org/api/v2/data/dataflow/BIS/WS_XRU/1.0/D.{area}.{currency}.A"
BIS_ACCEPT = "application/vnd.sdmx.data+csv;version=1.0.0"
ECB_URL = "https://www.ecb.europa.eu/stats/eurofxref/eurofxref-hist.zip"
ECB_MEMBER = "eurofxref-hist.csv"
STALE_DAYS = 5
TRANSIENT_STATUS = (429, 500, 502, 503, 504)

# The AUD was pegged to sterling until December 1971. The ratio is measured on
# the first months of observed BIS AUD data and applied to observed 1970 sterling.
PEG_WINDOW = (date(1971, 1, 4), date(1971, 6, 30))
PEG_MAX_SPREAD = Decimal("0.003")
SPLICE_TOLERANCE = Decimal("0.00001")  # BIS stores six decimals of the inverse quote.
MAX_DAILY_MOVE = Decimal("0.25")

ECB_SOURCE = "ECB euro foreign exchange reference rates"
BIS_SOURCE = "BIS bilateral exchange rates WS_XRU (daily, local currency per USD)"


@dataclass(frozen=True)
class Pair:
    stem: str
    alias: str
    name: str
    currency: str
    bis_area: str
    bis_currency: str
    ecb_flag: str
    ecb_notes: str
    bis_flag: str
    bis_notes: str


PAIRS = {
    "fx_aud_usd": Pair(
        "fx_aud_usd", "AUDUSD", "Australian dollar spot rate, USD per AUD", "AUD", "AU", "AUD",
        "observed_ecb_reference_rate_cross_aud_usd",
        "USD per AUD as the cross of the ECB USD/EUR and AUD/EUR reference rates set around 14:15 CET. "
        "Spot rate only; no interest carry.",
        "observed_bis_daily_aud_usd",
        "USD per AUD as the inverse of the BIS daily AUD-per-USD rate. Spot rate only; no interest carry.",
    ),
    "fx_eur_usd": Pair(
        "fx_eur_usd", "EURUSD", "Euro spot rate, USD per EUR", "EUR", "DE", "EUR",
        "observed_ecb_reference_rate_eur_usd",
        "USD per EUR, the ECB reference rate set around 14:15 CET. Spot rate only; no interest carry.",
        "proxy_bis_deutsche_mark_at_fixed_euro_conversion_rate",
        "USD per EUR before the euro existed: inverse of the BIS German series, which is the observed "
        "Deutsche Mark rate converted at the fixed 1.95583 DEM per EUR. Spot rate only; no interest carry.",
    ),
    "fx_gbp_usd": Pair(
        "fx_gbp_usd", "GBPUSD", "Pound sterling spot rate, USD per GBP", "GBP", "GB", "GBP",
        "observed_ecb_reference_rate_cross_gbp_usd",
        "USD per GBP as the cross of the ECB USD/EUR and GBP/EUR reference rates set around 14:15 CET. "
        "Spot rate only; no interest carry.",
        "observed_bis_daily_gbp_usd",
        "USD per GBP as the inverse of the BIS daily GBP-per-USD rate. Spot rate only; no interest carry.",
    ),
}
PEG_FLAG = "model_sterling_peg_cross_from_bis_gbp_usd"
PEG_SOURCE = "BIS bilateral exchange rates WS_XRU (daily GBP per USD) and the 1971 AUD/GBP peg ratio"
PEG_NOTES = (
    "Modeled: BIS has no daily AUD observation before 1971-01-04. USD per AUD is the observed daily "
    "BIS sterling rate divided by the median AUD-per-GBP ratio observed from 1971-01-04 to 1971-06-30, "
    "when the AUD was pegged to sterling. Spot rate only; no interest carry."
)


def round_number(value: Decimal) -> str:
    result = f"{value:.10f}".rstrip("0").rstrip(".")
    return "0" if result in ("", "-0") else result


def checksum_bytes(content: bytes) -> str:
    return hashlib.sha256(content).hexdigest()


def session_with_retries() -> requests.Session:
    session = requests.Session()
    retry = Retry(total=3, backoff_factor=2, status_forcelist=TRANSIENT_STATUS,
                  allowed_methods=frozenset({"GET"}), respect_retry_after_header=True)
    session.mount("https://", HTTPAdapter(max_retries=retry))
    session.headers.update({"User-Agent": "financial_datasets/1.0 (+https://github.com/mwilczynska/financial_datasets)"})
    return session


# --- ECB -----------------------------------------------------------------

def parse_ecb(content: bytes) -> dict[str, dict[str, Decimal]]:
    """Return ``{date: {currency: units per EUR}}`` from the ECB history ZIP."""
    with zipfile.ZipFile(io.BytesIO(content)) as archive:
        if archive.namelist() != [ECB_MEMBER]:
            raise RuntimeError(f"ECB archive has unexpected members: {archive.namelist()}")
        text = archive.read(ECB_MEMBER).decode("utf-8-sig")
    reader = csv.reader(io.StringIO(text))
    header = [cell.strip() for cell in next(reader)]
    if header[0] != "Date" or any(code not in header for code in ("USD", "GBP", "AUD")):
        raise RuntimeError(f"ECB reference-rate file has unexpected columns: {header[:6]}")
    columns = {code: header.index(code) for code in ("USD", "GBP", "AUD")}
    rates: dict[str, dict[str, Decimal]] = {}
    for record in reader:
        if not record or not record[0].strip():
            continue
        day = record[0].strip()
        date.fromisoformat(day)
        if day in rates:
            raise RuntimeError(f"Duplicate ECB reference-rate date: {day}")
        values: dict[str, Decimal] = {}
        for code, index in columns.items():
            raw = record[index].strip() if index < len(record) else ""
            if raw in ("", "N/A"):
                continue
            value = Decimal(raw)
            if not value.is_finite() or value <= 0:
                raise RuntimeError(f"Invalid ECB {code} reference rate on {day}")
            values[code] = value
        rates[day] = values
    if not rates:
        raise RuntimeError("ECB reference-rate file has no observations")
    return dict(sorted(rates.items()))


def ecb_series(pair: Pair, rates: dict[str, dict[str, Decimal]]) -> dict[str, Decimal]:
    """USD per unit of the pair's currency on every day both legs were published."""
    series: dict[str, Decimal] = {}
    for day, values in rates.items():
        if day < ECB_START.isoformat() or "USD" not in values:
            continue
        if pair.currency == "EUR":
            series[day] = values["USD"]
        elif pair.currency in values:
            series[day] = values["USD"] / values[pair.currency]
    return series


def fetch_ecb(session: requests.Session) -> bytes:
    response = session.get(ECB_URL, timeout=(10, 60))
    response.raise_for_status()
    return response.content


# --- BIS -----------------------------------------------------------------

def parse_bis(text: str, area: str, currency: str) -> dict[str, Decimal]:
    """Return ``{date: local currency per USD}``; BIS marks non-observation days ``NaN``."""
    reader = csv.DictReader(io.StringIO(text.lstrip("﻿")))
    required = {"FREQ", "REF_AREA", "CURRENCY", "COLLECTION", "TIME_PERIOD", "OBS_VALUE"}
    if not reader.fieldnames or not required <= set(reader.fieldnames):
        raise RuntimeError(f"BIS response has unexpected columns: {reader.fieldnames}")
    series: dict[str, Decimal] = {}
    for row in reader:
        if (row["FREQ"], row["REF_AREA"], row["CURRENCY"], row["COLLECTION"]) != ("D", area, currency, "A"):
            raise RuntimeError(f"BIS response has an unexpected series key on {row['TIME_PERIOD']}")
        day = row["TIME_PERIOD"]
        date.fromisoformat(day)
        if day in series:
            raise RuntimeError(f"Duplicate BIS date: {day}")
        if row["OBS_VALUE"] in ("NaN", ""):
            continue
        value = Decimal(row["OBS_VALUE"])
        if not value.is_finite() or value <= 0:
            raise RuntimeError(f"Invalid BIS {area}.{currency} rate on {day}")
        series[day] = value
    return series


def fetch_bis(session: requests.Session, area: str, currency: str) -> str:
    """Fetch 1969-12 to 1999 in decade chunks; single long responses have arrived truncated."""
    header = ""
    body: list[str] = []
    start = BIS_FETCH_START
    while start <= BIS_FETCH_END:
        end = min(date(start.year + 10, 12, 31) if start.month == 12 else date(start.year + 9, 12, 31), BIS_FETCH_END)
        response = session.get(BIS_URL.format(area=area, currency=currency),
                               params={"startPeriod": start.isoformat(), "endPeriod": end.isoformat()},
                               headers={"Accept": BIS_ACCEPT}, timeout=(10, 120))
        response.raise_for_status()
        lines = response.text.lstrip("﻿").splitlines()
        chunk = parse_bis("\n".join(lines), area, currency)
        requested_first = max(start, date(1971, 1, 4)) if area == "AU" else start
        if not chunk or (date.fromisoformat(min(chunk)) - requested_first).days > 10 \
                or (end - date.fromisoformat(max(chunk))).days > 10:
            raise RuntimeError(f"BIS {area}.{currency} chunk {start}..{end} is empty or truncated")
        header = header or lines[0]
        if lines[0] != header:
            raise RuntimeError("BIS chunk headers differ")
        body.extend(lines[1:])
        start = end + timedelta(days=1)
    return "\n".join([header, *body]) + "\n"


def load_bis(raw_dir: Path, session: requests.Session, area: str, currency: str,
             refresh: bool) -> tuple[dict[str, Decimal], dict]:
    path = raw_dir / f"fx_rates_bis_xru_{area.lower()}_{currency.lower()}.csv"
    if refresh or not path.is_file():
        text = fetch_bis(session, area, currency)
        raw_dir.mkdir(parents=True, exist_ok=True)
        path.write_text(text, encoding="utf-8", newline="\n")
    content = path.read_bytes()
    series = parse_bis(content.decode("utf-8"), area, currency)
    record = {"url": BIS_URL.format(area=area, currency=currency), "series": f"D.{area}.{currency}.A",
              "path": f"sources/raw/{path.name}", "sha256": checksum_bytes(content),
              "first_date": min(series), "last_date": max(series), "observations": len(series)}
    return series, record


# --- Rows ----------------------------------------------------------------

def make_rows(levels: list[tuple[str, Decimal, str, str, str]],
              previous_close: str | None = None) -> list[dict[str, str]]:
    """Build output rows from ``(date, USD per unit, source, flag, notes)`` tuples."""
    rows: list[dict[str, str]] = []
    for day, level, source, flag, notes in levels:
        close = round_number(level)
        if Decimal(close) <= 0:
            raise RuntimeError(f"Non-positive exchange rate on {day}")
        change = "" if previous_close is None else round_number(Decimal(close) / Decimal(previous_close) - 1)
        if change and abs(Decimal(change)) > MAX_DAILY_MOVE:
            raise RuntimeError(f"Implausible exchange-rate move on {day}: {change}")
        row = {key: "" for key in OUTPUT_COLUMNS}
        row.update({"Date": day, "Close": close, "Adj Close": close, "Price Return": change,
                    "Total Return": change, "Source": source, "Quality Flag": flag, "Source Notes": notes})
        rows.append(row)
        previous_close = close
    return rows


def peg_ratio(aud: dict[str, Decimal], gbp: dict[str, Decimal]) -> Decimal:
    days = [day for day in aud if PEG_WINDOW[0].isoformat() <= day <= PEG_WINDOW[1].isoformat() and day in gbp]
    ratios = [aud[day] / gbp[day] for day in days]
    if len(ratios) < 100 or (max(ratios) - min(ratios)) / min(ratios) > PEG_MAX_SPREAD:
        raise RuntimeError("1971 AUD/GBP observations do not show the expected sterling peg")
    return Decimal(statistics.median(ratios))


def historical_levels(pair: Pair, bis: dict[str, Decimal], ecb: dict[str, Decimal],
                      gbp: dict[str, Decimal] | None = None) -> tuple[list[tuple[str, Decimal, str, str, str]], dict]:
    """Assemble the full level history and check the 1999 BIS/ECB splice."""
    start, switch = START_DATE.isoformat(), ECB_START.isoformat()
    details: dict = {}
    levels: list[tuple[str, Decimal, str, str, str]] = []
    first_bis = min(bis)
    if first_bis > start:
        if gbp is None:
            raise RuntimeError(f"{pair.stem}: BIS history starts {first_bis} and no peg model is defined")
        ratio = peg_ratio(bis, gbp)
        details["sterling_peg"] = {"aud_per_gbp_ratio": round_number(ratio),
                                   "calibration_window": [day.isoformat() for day in PEG_WINDOW],
                                   "modeled_through": max(day for day in gbp if day < first_bis)}
        levels.extend((day, Decimal(1) / (value * ratio), PEG_SOURCE, PEG_FLAG, PEG_NOTES)
                      for day, value in gbp.items() if start <= day < first_bis)
    levels.extend((day, Decimal(1) / value, BIS_SOURCE, pair.bis_flag, pair.bis_notes)
                  for day, value in bis.items() if max(start, first_bis) <= day < switch)
    overlap = [day for day in bis if day >= switch and day in ecb]
    worst = max((abs(Decimal(1) / bis[day] / ecb[day] - 1) for day in overlap), default=Decimal(1))
    if len(overlap) < 200 or worst > SPLICE_TOLERANCE:
        raise RuntimeError(f"{pair.stem}: BIS and ECB disagree on the 1999 overlap ({len(overlap)} days, {worst})")
    details["bis_ecb_overlap"] = {"days": len(overlap), "first_date": min(overlap), "last_date": max(overlap),
                                  "max_relative_difference": f"{worst:.3E}"}
    levels.extend((day, value, ECB_SOURCE, pair.ecb_flag, pair.ecb_notes) for day, value in ecb.items())
    days = [level[0] for level in levels]
    if days != sorted(set(days)) or days[0] != start:
        raise RuntimeError(f"{pair.stem}: history is unsorted, duplicated, or does not start on {start}")
    return levels, details


def write_csv(path: Path, rows: list[dict[str, str]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    with temporary.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=OUTPUT_COLUMNS, lineterminator="\n")
        writer.writeheader()
        writer.writerows(rows)
    temporary.replace(path)


def write_parquet(csv_path: Path, parquet_path: Path) -> None:
    import pandas as pd
    frame = pd.read_csv(csv_path, parse_dates=["Date"])
    temporary = parquet_path.with_suffix(parquet_path.suffix + ".tmp")
    frame.to_parquet(temporary, index=False)
    temporary.replace(parquet_path)


# --- Full historical build -----------------------------------------------

def build(stem: str, root: Path, end: date, refresh: bool = False,
          session: requests.Session | None = None) -> list[dict[str, str]]:
    pair = PAIRS[stem]
    session = session or session_with_retries()
    raw_dir = root / "sources" / "raw"
    bis, bis_record = load_bis(raw_dir, session, pair.bis_area, pair.bis_currency, refresh)
    sources = {"BIS_WS_XRU": bis_record}
    gbp = None
    if min(bis) > START_DATE.isoformat():
        gbp, sources["BIS_WS_XRU_GBP"] = load_bis(raw_dir, session, "GB", "GBP", refresh)
    ecb_content = fetch_ecb(session)
    raw_dir.mkdir(parents=True, exist_ok=True)
    ecb_path = raw_dir / f"{stem}_ecb_eurofxref_hist.zip"
    ecb_path.write_bytes(ecb_content)
    ecb = {day: value for day, value in ecb_series(pair, parse_ecb(ecb_content)).items() if day <= end.isoformat()}
    if not ecb or (end - date.fromisoformat(max(ecb))).days > STALE_DAYS:
        raise RuntimeError(f"{stem}: ECB reference rates are stale for {end}")
    sources["ECB_EUROFXREF"] = {"url": ECB_URL, "path": f"sources/raw/{ecb_path.name}",
                                "sha256": checksum_bytes(ecb_content), "first_date": min(ecb), "last_date": max(ecb),
                                "accessed_at_utc": datetime.now(timezone.utc).isoformat()}
    levels, details = historical_levels(pair, bis, ecb, gbp)
    rows = make_rows(levels)
    csv_path = root / "data" / "processed" / f"{stem}.csv"
    write_csv(root / "data" / "interim" / f"{stem}.csv", rows)
    write_csv(csv_path, rows)
    write_parquet(csv_path, csv_path.with_suffix(".parquet"))
    flags = sorted({row["Quality Flag"] for row in rows})
    metadata = {
        "asset_id": stem, "asset_name": pair.name, "alias": pair.alias,
        "quote_convention": f"USD per 1 {pair.currency}",
        "build_timestamp_utc": datetime.now(timezone.utc).isoformat(),
        "row_count": len(rows), "first_date": rows[0]["Date"], "last_date": rows[-1]["Date"],
        "csv_path": f"data/processed/{stem}.csv", "csv_sha256": checksum_bytes(csv_path.read_bytes()),
        "parquet_written": True, "quality_flags": flags,
        "segment_row_counts": {flag: sum(row["Quality Flag"] == flag for row in rows) for flag in flags},
        "historical_sources": sources, **details,
        "notes": "Spot exchange rate. Adj Close equals Close; the series carries no interest income.",
    }
    path = root / "sources" / "manifests" / f"{stem}_build.json"
    path.write_text(json.dumps(metadata, indent=2) + "\n", encoding="utf-8")
    print(f"{stem}: wrote {len(rows)} rows, {rows[0]['Date']} to {rows[-1]['Date']}")
    for flag, count in metadata["segment_row_counts"].items():
        print(f"  {flag}: {count}")
    return rows


def build_main(stem: str) -> None:
    parser = argparse.ArgumentParser(description=f"Build the full {PAIRS[stem].alias} history from BIS and ECB.")
    parser.add_argument("--end-date", default=date.today().isoformat(), help="Inclusive end date, YYYY-MM-DD.")
    parser.add_argument("--root", default=str(PROJECT_ROOT), help="Project root.")
    parser.add_argument("--refresh-historical-sources", action="store_true",
                        help="Refetch the cached BIS history instead of reusing sources/raw.")
    parser.add_argument("--refresh-static-sources", action="store_true", help=argparse.SUPPRESS)
    args = parser.parse_args()
    build(stem, Path(args.root).resolve(), date.fromisoformat(args.end_date),
          refresh=args.refresh_historical_sources or args.refresh_static_sources)


# --- Incremental update and publication gate -----------------------------

def recent_path(root: Path, stem: str) -> Path:
    return root / "sources" / "raw" / "incremental" / f"{stem}_ecb_eurofxref_hist.zip"


def recent_rows(pair: Pair, existing: list[dict[str, str]], ecb: dict[str, Decimal],
                end: date, overlap_days: int) -> tuple[list[dict[str, str]], str]:
    """Recalculate the rows after the overlap anchor from the ECB series."""
    last = date.fromisoformat(existing[-1]["Date"])
    candidates = [row for row in existing if row["Date"] < (last - timedelta(days=overlap_days)).isoformat()]
    if not candidates:
        raise RuntimeError(f"No {pair.stem} overlap anchor; use the full builder")
    anchor = candidates[-1]
    anchor_day = anchor["Date"]
    if anchor["Quality Flag"] != pair.ecb_flag:
        raise RuntimeError(f"{pair.stem} is not in its ECB reference-rate segment at {anchor_day}")
    if anchor_day not in ecb or abs(ecb[anchor_day] - Decimal(anchor["Close"])) > Decimal("1e-9"):
        raise RuntimeError(f"{pair.stem}: ECB disagrees with the committed overlap anchor {anchor_day}")
    days = [day for day in ecb if anchor_day < day <= end.isoformat()]
    missing = sorted({row["Date"] for row in existing if row["Date"] > anchor_day} - set(days))
    if missing:
        raise RuntimeError(f"{pair.stem} source would delete committed dates: {missing[:5]}")
    recent = make_rows([(day, ecb[day], ECB_SOURCE, pair.ecb_flag, pair.ecb_notes) for day in days],
                       previous_close=anchor["Close"])
    return [row for row in existing if row["Date"] <= anchor_day] + recent, anchor_day


def update_recent(root: Path, stem: str, existing: list[dict[str, str]], end: date, overlap_days: int,
                  session: requests.Session) -> tuple[list[dict[str, str]], dict[str, dict], str]:
    """Fetch the ECB file, keep it for the publication gate, and return the candidate rows."""
    pair = PAIRS[stem]
    content = fetch_ecb(session)
    ecb = ecb_series(pair, parse_ecb(content))
    rows, anchor_day = recent_rows(pair, existing, ecb, end, overlap_days)
    if (end - date.fromisoformat(rows[-1]["Date"])).days > STALE_DAYS:
        raise RuntimeError(f"{stem}: ECB reference rates are stale for {end}: {rows[-1]['Date']}")
    path = recent_path(root, stem)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(content)
    record = {"url": ECB_URL, "path": path.relative_to(root).as_posix(), "sha256": checksum_bytes(content),
              "first_date": min(ecb), "last_date": max(ecb),
              "accessed_at_utc": datetime.now(timezone.utc).isoformat()}
    return rows, {"ECB_EUROFXREF": record}, anchor_day


def check_recent(root: Path, stem: str, rows: list[dict[str, str]], end: date, examined_days: set[str]) -> None:
    """Publication gate: the tail must equal the saved, current ECB response."""
    pair = PAIRS[stem]
    path = recent_path(root, stem)
    if not path.is_file():
        raise RuntimeError(f"{stem}: missing current ECB reference-rate response")
    ecb = {day: value for day, value in ecb_series(pair, parse_ecb(path.read_bytes())).items()
           if day <= end.isoformat()}
    if not ecb or (end - date.fromisoformat(max(ecb))).days > STALE_DAYS:
        raise RuntimeError(f"{stem}: ECB reference-rate response is stale for {end}")
    if rows[-1]["Date"] != max(ecb):
        raise RuntimeError(f"{stem}: last row {rows[-1]['Date']} differs from latest ECB date {max(ecb)}")
    examined = set(examined_days) | {row["Date"] for row in rows[-10:]}
    first = min(examined)
    if first < ECB_START.isoformat():
        raise RuntimeError(f"{stem}: examined rows precede the ECB segment")
    dates = [row["Date"] for row in rows if row["Date"] >= first]
    if dates != [day for day in ecb if day >= first]:
        raise RuntimeError(f"{stem}: recent dates differ from the ECB reference-rate calendar")
    for row in rows:
        if row["Date"] not in examined:
            continue
        if row["Quality Flag"] != pair.ecb_flag or row["Adj Close"] != row["Close"]:
            raise RuntimeError(f"{stem}: unexpected flag or adjusted close on {row['Date']}")
        if abs(Decimal(row["Close"]) - ecb[row["Date"]]) > Decimal("1e-9"):
            raise RuntimeError(f"{stem}: rate disagrees with the ECB reference rate on {row['Date']}")
