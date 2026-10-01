"""Pinned daily GSCI Spot/ER/TR snapshot and published-reference checks.

The public workbook is an author-claimed Bloomberg extraction, not an
authenticated vendor feed. Before the May 1, 1991 launch its index history is
provider back-calculation. Weekday holidays may carry the previous value.
Public availability does not establish redistribution rights.
"""

from __future__ import annotations

import csv
import hashlib
import json
from datetime import date, datetime, timedelta, timezone
from decimal import Decimal
from pathlib import Path

import requests
from openpyxl import load_workbook


COMMIT = "f5ecf1507fb9cc98ffcc1f69c217793f5f9272a3"
URL = f"https://raw.githubusercontent.com/yessinemx/Trading_Commo/{COMMIT}/data/GSCI_Data.xlsx"
SHA256 = "918e4046300180e0274781bfa6f1f5dcf2dc7df61b9229f9d4a9ea124da2a9f8"
BYTE_COUNT = 442834
RAW_FILE = "broad_commodities_gsci_daily.xlsx"
SHEET = "Données GSCI"
COLUMNS = ("Date", "GSCI_Spot", "GSCI_ER", "GSCI_TR")
FIRST_DATE = "1970-01-02"
LAST_DATE = "2025-12-31"
SPLICE_DATE = "1991-01-02"
CALENDAR_FILE = "sources/derived/broad_commodities_gsci_calendar.csv"
CALENDAR_MANIFEST = "sources/derived/broad_commodities_gsci_calendar.json"
RIGHTS = "No verified grant to redistribute Bloomberg/S&P observations or derived outputs."

# Kaplan/Lummer Appendix A, PDF p. 13, and SEC Release 34-53658, pp. 29-30.
# References corroborate the same index history, not every daily observation.
ANNUAL_TR = {
    1970: 15.10, 1971: 21.08, 1972: 42.43, 1973: 74.96, 1974: 39.51,
    1975: -17.22, 1976: -11.92, 1977: 10.37, 1978: 31.61, 1979: 33.81,
    1980: 11.08, 1981: -23.01, 1982: 11.56, 1983: 16.26, 1984: 1.05,
    1985: 10.01, 1986: 2.04, 1987: 23.77, 1988: 27.93, 1989: 38.28,
    1990: 29.08, 1991: -6.13,
}
SEC_TR = {
    "1970-01-02": 100, "1971-01-04": 115.78, "1972-01-03": 138.90,
    "1973-01-02": 198.45, "1974-01-02": 354.32, "1975-01-02": 478.50,
    "1976-01-02": 400.02, "1977-01-03": 351.05, "1978-01-03": 390.02,
    "1979-01-02": 515.25, "1980-01-02": 692.40, "1981-01-02": 764.66,
    "1982-01-04": 593.61, "1983-01-03": 657.98, "1984-01-03": 747.23,
    "1985-01-03": 760.67, "1986-01-02": 833.67, "1987-01-02": 868.83,
    "1988-01-04": 1105.18, "1989-01-03": 1371.33, "1990-01-02": 1937.46,
    "1991-01-02": 2346.03,
}


def checksum(path: Path) -> str:
    with path.open("rb") as handle:
        return hashlib.file_digest(handle, "sha256").hexdigest()


def verify_snapshot(path: Path) -> None:
    if path.stat().st_size != BYTE_COUNT or checksum(path) != SHA256:
        raise ValueError(f"GSCI source differs from the reviewed snapshot: {path}")


def acquire(root: Path) -> tuple[Path, str]:
    """Reuse the verified research cache or fetch the exact reviewed version."""
    path = root / "sources/raw" / RAW_FILE
    if path.exists():
        verify_snapshot(path)
        return path, "cached"
    path.parent.mkdir(parents=True, exist_ok=True)
    research = root / "sources/raw/cmdty_1970s_research/trading_commo_data.xlsx"
    if research.exists():
        verify_snapshot(research)
        payload = research.read_bytes()
        source_sidecar = research.with_suffix(".xlsx.retrieval.json")
        timing = json.loads(source_sidecar.read_text(encoding="utf-8")) if source_sidecar.exists() else {}
        mode = "copied_verified_research_snapshot"
    else:
        response = requests.get(URL, timeout=60, headers={"User-Agent": "Mozilla/5.0"})
        response.raise_for_status()
        payload = response.content
        timing = {"retrieved_utc": datetime.now(timezone.utc).isoformat()}
        mode = "fetched_pinned_snapshot"
    if len(payload) != BYTE_COUNT or hashlib.sha256(payload).hexdigest() != SHA256:
        raise ValueError("Downloaded GSCI workbook differs from the reviewed snapshot")
    path.write_bytes(payload)
    path.with_suffix(".xlsx.retrieval.json").write_text(json.dumps({
        **timing, "requested_url": URL, "sha256": SHA256, "bytes": BYTE_COUNT,
        "cached_utc": datetime.now(timezone.utc).isoformat(), "mode": mode,
        "observed_coverage": [FIRST_DATE, LAST_DATE], "rights": RIGHTS,
    }, indent=2) + "\n", encoding="utf-8")
    return path, mode


def load_snapshot(path: Path) -> list[dict]:
    verify_snapshot(path)
    book = load_workbook(path, read_only=True, data_only=True)
    try:
        cells = book[SHEET].iter_rows(values_only=True)
        if tuple(next(cells)) != COLUMNS:
            raise ValueError("Unexpected GSCI workbook schema")
        rows = []
        for cell in cells:
            stamp = cell[0]
            if not isinstance(stamp, datetime) or stamp.time() != datetime.min.time():
                raise ValueError(f"Invalid GSCI date: {stamp!r}")
            row = {"Date": stamp.date().isoformat()}
            for name, value in zip(COLUMNS[1:], cell[1:]):
                level = Decimal(str(value))
                if not level.is_finite() or level <= 0:
                    raise ValueError(f"GSCI {name} must be finite and positive on {row['Date']}")
                row[name] = level
            rows.append(row)
    finally:
        book.close()
    expected = []
    day, last = date.fromisoformat(FIRST_DATE), date.fromisoformat(LAST_DATE)
    while day <= last:
        if day.weekday() < 5:
            expected.append(day.isoformat())
        day += timedelta(days=1)
    if [row["Date"] for row in rows] != expected:
        raise ValueError("GSCI snapshot must have the complete, ordered weekday calendar")
    if any(rows[0][name] != 100 for name in COLUMNS[1:]):
        raise ValueError("GSCI source series must each start at 100")
    published_reference_checks(rows)
    return rows


def published_reference_checks(rows: list[dict]) -> dict:
    """Fail if any of the 44 reviewed references exceeds published rounding."""
    tr = {row["Date"]: Decimal(str(row["GSCI_TR"])) for row in rows}
    dates = sorted(tr)
    annual_errors = []
    for year, target in ANNUAL_TR.items():
        previous = [day for day in dates if day < f"{year}-01-01"]
        current = [day for day in dates if day.startswith(str(year))]
        if not current:
            raise ValueError(f"GSCI missing annual reference year {year}")
        base = tr[previous[-1]] if previous else tr[FIRST_DATE]
        actual = 100 * (tr[current[-1]] / base - 1)
        error = abs(actual - Decimal(str(target)))
        if error >= Decimal("0.0050000001"):
            raise ValueError(f"GSCI fails annual TR reference for {year}: {actual}")
        annual_errors.append(error)
    level_errors = []
    for day, target in SEC_TR.items():
        if day not in tr:
            raise ValueError(f"GSCI missing dated SEC reference {day}")
        error = abs(tr[day] - Decimal(str(target)))
        if error >= Decimal("0.0050000001"):
            raise ValueError(f"GSCI fails SEC TR level reference on {day}")
        level_errors.append(error)
    return {
        "annual_tr_checks_passed": len(annual_errors), "sec_tr_level_checks_passed": len(level_errors),
        "max_annual_error_percentage_points": float(max(annual_errors)),
        "max_sec_level_error": float(max(level_errors)),
        "annual_reference_url": "https://www.etf.com/docs/20040913_GSCI.pdf",
        "sec_reference_url": "https://www.sec.gov/files/rules/sro/nyse/2006/34-53658.pdf",
    }


def load_calendar(root: Path) -> list[str]:
    path = root / CALENDAR_FILE
    metadata = json.loads((root / CALENDAR_MANIFEST).read_text(encoding="utf-8"))
    if checksum(path) != metadata["sha256"]:
        raise ValueError("CMDTY GSCI calendar differs from its preserved manifest")
    with path.open(newline="", encoding="utf-8") as handle:
        reader = csv.DictReader(handle)
        if reader.fieldnames != ["Date"]:
            raise ValueError("Unexpected CMDTY GSCI calendar schema")
        dates = [row["Date"] for row in reader]
    if (not dates or dates != sorted(set(dates)) or dates[0] != FIRST_DATE
            or dates[-1] != SPLICE_DATE or len(dates) != metadata["row_count"]):
        raise ValueError("Invalid preserved CMDTY GSCI calendar")
    if any(date.fromisoformat(day).weekday() >= 5 for day in dates):
        raise ValueError("CMDTY GSCI calendar contains a weekend")
    return dates


def source_metadata(root: Path, path: Path, mode: str, rows: list[dict]) -> dict:
    sidecar = path.with_suffix(".xlsx.retrieval.json")
    timing = json.loads(sidecar.read_text(encoding="utf-8")) if sidecar.exists() else {}
    return {
        "url": URL, "commit": COMMIT, "path": path.relative_to(root).as_posix(),
        "sha256": SHA256, "bytes": BYTE_COUNT, "mode": mode,
        "retrieved_utc": timing.get("retrieved_utc"), "sheet": SHEET,
        "source_columns": {"Close": "GSCI_ER", "Adj Close": "GSCI_TR"},
        "observed_rows": len(rows), "observed_first_date": FIRST_DATE, "observed_last_date": LAST_DATE,
        "used_first_date": FIRST_DATE, "used_last_date": SPLICE_DATE,
        "provenance": "Public author-claimed Bloomberg PX_LAST extraction; original terminal extraction not authenticated.",
        "fill": "NON_TRADING_WEEKDAYS / PREVIOUS_VALUE; holidays may carry the previous level.",
        "index_launch_date": "1991-05-01", "early_history": "provider_back_calculated",
        "redistribution_rights": RIGHTS, "reference_checks": published_reference_checks(rows),
    }
