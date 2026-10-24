"""Retrieve the same monthly BLS CPI series through independently hosted delivery routes."""

from __future__ import annotations

import csv
import hashlib
import io
import json
import math
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

import requests

try:
    from . import build_cpi_inflation as cpi
except ImportError:
    import build_cpi_inflation as cpi


FRED_SERIES = "CPIAUCSL"
FRED_URL = "https://fred.stlouisfed.org/graph/fredgraph.csv"
TRANSIENT_STATUS = (429, 500, 502, 503, 504)
SOURCE_FILES = {
    "BLS_CUSR0000SA0": "sources/raw/incremental/cpi_bls_recent.json",
    "FRED_CPIAUCSL": "sources/raw/incremental/cpi_fred_recent.csv",
}


def parse_fred_monthly(content: str, start_year: int, end: date) -> list[tuple[date, float]]:
    reader = csv.DictReader(io.StringIO(content.lstrip("\ufeff")))
    if reader.fieldnames not in (["observation_date", FRED_SERIES], ["DATE", FRED_SERIES]):
        raise RuntimeError(f"FRED response has unexpected CPI series/columns: {reader.fieldnames}")
    date_column = reader.fieldnames[0]
    monthly = []
    for row in reader:
        day = date.fromisoformat(row[date_column])
        if day.year < start_year or day > end:
            continue
        value = float(row[FRED_SERIES])
        if day.day != 1 or not math.isfinite(value) or value <= 0:
            raise RuntimeError(f"Invalid FRED CPI observation on {day}")
        monthly.append((day, value))
    return validate_monthly(monthly, end)


def validate_monthly(monthly: list[tuple[date, float]], end: date) -> list[tuple[date, float]]:
    days = [day for day, _ in monthly]
    if not days or days != sorted(set(days)):
        raise RuntimeError("CPI monthly source has empty, duplicate, or unsorted observations")
    if any(day.day != 1 or day > end or not math.isfinite(value) or value <= 0 for day, value in monthly):
        raise RuntimeError("CPI monthly source has invalid dates or levels")
    for left, right in zip(days, days[1:]):
        if right.year * 12 + right.month != left.year * 12 + left.month + 1:
            raise RuntimeError("CPI monthly source has missing months")
    if (end - days[-1]).days > 90:
        raise RuntimeError(f"CPI monthly source is stale: {days[-1]}")
    return monthly


def validate_fred_overlap(monthly: list[tuple[date, float]], existing: list[dict[str, str]],
                          previous_monthly: date) -> None:
    observed = {date.fromisoformat(row["Date"]): float(row["Close"]) for row in existing
                if row["Quality Flag"] == cpi.MONTHLY_FLAG}
    values = dict(monthly)
    overlap = [day for day in observed if monthly[0][0] <= day <= previous_monthly]
    if previous_monthly not in values or previous_monthly not in observed or len(overlap) < 3:
        raise RuntimeError("FRED CPI lacks the committed monthly anchor and three-month overlap")
    if any(day not in values or abs(values[day] - observed[day]) > 1e-9 for day in overlap):
        raise RuntimeError("FRED CPI disagrees with committed BLS monthly observations")


def parse_bls_recent(body: dict, end: date) -> list[tuple[date, float]]:
    if body.get("status") != "REQUEST_SUCCEEDED":
        raise RuntimeError(f"BLS recent CPI request failed: {body}")
    series = body.get("Results", {}).get("series", [])
    if len(series) != 1 or series[0].get("seriesID") != cpi.BLS_SERIES:
        raise RuntimeError("BLS response has a missing or incorrect CPI series ID")
    return validate_monthly(cpi.parse_bls_monthly([body]), end)


def fetch_recent_monthly(root: Path, existing: list[dict[str, str]], previous_monthly: date,
                         end: date, session: requests.Session) -> tuple[list[tuple[date, float]], dict]:
    start_year = max(1970, previous_monthly.year - 1)
    payload = {"seriesid": [cpi.BLS_SERIES], "startyear": str(start_year), "endyear": str(end.year)}
    fallback_reason = None
    try:
        response = session.post(cpi.BLS_API_URL, json=payload, timeout=60)
        response.raise_for_status()
    except requests.RequestException as error:
        transient = isinstance(error, (requests.ConnectionError, requests.Timeout, requests.exceptions.RetryError))
        if isinstance(error, requests.HTTPError) and error.response is not None:
            transient = error.response.status_code in TRANSIENT_STATUS
        if not transient:
            raise
        fallback_reason = str(error)
        print(f"BLS CPI temporarily unavailable; checking FRED {FRED_SERIES}: {error}", flush=True)
        response = session.get(FRED_URL, params={"id": FRED_SERIES, "cosd": f"{start_year}-01-01",
                                               "coed": end.isoformat()}, timeout=60)
        response.raise_for_status()
        content = response.content
        monthly = parse_fred_monthly(content.decode("utf-8-sig"), start_year, end)
        validate_fred_overlap(monthly, existing, previous_monthly)
        key, url, series_id = "FRED_CPIAUCSL", FRED_URL, FRED_SERIES
    else:
        body = response.json()
        monthly = parse_bls_recent(body, end)
        content = json.dumps(body).encode("utf-8")
        key, url, series_id = "BLS_CUSR0000SA0", cpi.BLS_API_URL, cpi.BLS_SERIES
    if previous_monthly not in dict(monthly):
        raise RuntimeError(f"CPI response omitted committed monthly anchor {previous_monthly}")
    path = root / SOURCE_FILES[key]
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(content)
    record = {"url": url, "path": SOURCE_FILES[key], "series_id": series_id,
              "sha256": hashlib.sha256(content).hexdigest(),
              "accessed_at_utc": datetime.now(timezone.utc).isoformat(),
              "requested_end_date": end.isoformat(), "first_date": monthly[0][0].isoformat(),
              "last_date": monthly[-1][0].isoformat()}
    if fallback_reason:
        record["fallback_reason"] = fallback_reason
        print(f"FRED CPI verified against committed BLS overlap; latest month {monthly[-1][0]}", flush=True)
    return monthly, {key: record}


def load_recent_monthly(root: Path, records: dict, end: date,
                        baseline: list[dict[str, str]]) -> list[tuple[date, float]]:
    """Verify saved delivery provenance independently in the publication gate."""
    if len(records) != 1 or next(iter(records)) not in SOURCE_FILES:
        raise RuntimeError("Missing or unexpected current CPI source record")
    key, record = next(iter(records.items()))
    expected_url = cpi.BLS_API_URL if key == "BLS_CUSR0000SA0" else FRED_URL
    expected_series = cpi.BLS_SERIES if key == "BLS_CUSR0000SA0" else FRED_SERIES
    if (record.get("path") != SOURCE_FILES[key] or record.get("url") != expected_url
            or record.get("series_id") != expected_series or record.get("requested_end_date") != end.isoformat()):
        raise RuntimeError("CPI source provenance does not match the requested delivery route/date")
    accessed = datetime.fromisoformat(record["accessed_at_utc"])
    if accessed.tzinfo is None or not -timedelta(minutes=5) <= datetime.now(timezone.utc) - accessed <= timedelta(days=1):
        raise RuntimeError("CPI source response was not retrieved recently")
    content = (root / SOURCE_FILES[key]).read_bytes()
    if hashlib.sha256(content).hexdigest() != record.get("sha256"):
        raise RuntimeError("CPI source response hash disagrees with build metadata")
    if key == "BLS_CUSR0000SA0":
        monthly = parse_bls_recent(json.loads(content), end)
    else:
        previous = max(date.fromisoformat(row["Date"]) for row in baseline if row["Quality Flag"] == cpi.MONTHLY_FLAG)
        monthly = parse_fred_monthly(content.decode("utf-8-sig"), max(1970, previous.year - 1), end)
        validate_fred_overlap(monthly, baseline, previous)
    if record.get("first_date") != monthly[0][0].isoformat() or record.get("last_date") != monthly[-1][0].isoformat():
        raise RuntimeError("CPI source coverage disagrees with build metadata")
    return monthly
