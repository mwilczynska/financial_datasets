"""Build CMDTY from daily GSCI ER/TR, BCOM plus collateral, and DBC ETF returns.

1970-01-02 .. 1991-01-02: pinned daily GSCI ER/TR, on preserved CMDTY dates.
1991-01-03 .. 2006-02-06: BCOM excess return plus the existing IRX model.
2006-02-07 .. present: DBC ETF close and adjusted-close returns.
Close is excess-return growth before DBC and ETF price growth thereafter;
Adj Close is total-return growth. Both start at 100 and splice independently.
--migrate-gsci replaces the early source and rescales existing later levels
independently, preserving BCOM/DBC return ratios without historical Yahoo feeds.
Ordinary updates use update_broad_commodities.py.
"""
from __future__ import annotations

import argparse
import bisect
import csv
import hashlib
import io
import json
import math
import subprocess
from collections import Counter
from datetime import date, datetime, time, timedelta, timezone
from decimal import Decimal
from pathlib import Path
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

import requests

if __package__:
    from . import gsci_daily
else:
    import gsci_daily

ASSET_ID = "broad_commodities"
ASSET_NAME = "Broad Commodities / DBC-like Total Return"
START_DATE = date(1970, 1, 1)
BROAD_MODEL_START = date(1970, 1, 2)
BCOM_SYMBOL, DBC_SYMBOL, IRX_SYMBOL = "^BCOM", "DBC", "^IRX"
GSCI_END = gsci_daily.SPLICE_DATE
BCOM_FIRST_RETURN = "1991-01-03"
DBC_OVERLAP = "2006-02-06"
DBC_FIRST_RETURN = "2006-02-07"
HISTORICAL_CHARTS = {
    BCOM_SYMBOL: ("bcom", GSCI_END, DBC_OVERLAP, 3500),
    IRX_SYMBOL: ("irx", GSCI_END, DBC_OVERLAP, 3500),
}
GSCI_FLAG = "backcalculated_gsci_daily_excess_and_total_return"
BCOM_FLAG = "model_bcom_excess_return_plus_tbill_collateral"
DBC_FLAG = "observed_yahoo_dbc_dblci_total_return_etf"
LEGACY_GSCI_FLAGS = {
    "model_gsci_total_return_anchor_smoothed_daily",
    "model_gsci_total_return_anchor_with_spgsci_spot_daily_shape",
}
SOURCE = (
    "Pinned Trading_Commo public GSCI daily ER/TR workbook (author-claimed Bloomberg PX_LAST; "
    "provider back-calculated before 1991-05-01), on preserved CMDTY dates through 1991-01-02; "
    "Yahoo ^BCOM excess return plus ^IRX collateral through 2006-02-06; Yahoo DBC ETF thereafter"
)
GSCI_SOURCE = "S&P GSCI daily ER/TR via Trading_Commo public workbook (author-claimed Bloomberg extract)"
GSCI_NOTES = (
    "S&P GSCI daily EXCESS RETURN (Close: spot + roll) and TOTAL RETURN (Adj Close: ER + collateral), "
    "normalized separately to 100 at 1970-01-02. Provider back-calculated history before the "
    "1991-05-01 index launch. Public workbook author claims Bloomberg PX_LAST; terminal extraction "
    "not authenticated. Source uses previous-value fill on non-trading weekdays; holidays may carry "
    "levels. Sampled on preserved CMDTY dates before calculating returns. GSCI weights and roll "
    "differ from DBC. Redistribution rights remain unverified."
)
BCOM_NOTES = (
    "Bloomberg Commodity Excess Return Index via Yahoo ^BCOM (spot + roll yield; no collateral). "
    "Adj Close adds daily ^IRX T-bill collateral accrual (IRX%/100/365 per observation). "
    "Index methodology change from daily GSCI ER/TR at the 1991 boundary: different "
    "commodity weights and a different index family."
)
DBC_NOTES = (
    "DBC (Invesco DB Commodity Index Tracking Fund / DBLCI) observed ETF. "
    "Close compounds DBC daily close returns; Adj Close compounds DBC daily adjusted-close "
    "returns (Yahoo adj close captures accumulated T-bill collateral distributions). "
    "Index methodology change from BCOM Excess Return + T-bill model at the 2006 boundary. "
    "DBC uses optimum-yield rolling (different from BCOM roll rules). ~0.89% annual expense drag."
)
YAHOO_COLUMNS = ["Date", "Open", "High", "Low", "Close", "Adj Close", "Volume"]
PROJECT_COLUMNS = ["Price Return", "Total Return", "Source", "Quality Flag", "Source Notes"]
OUTPUT_COLUMNS = YAHOO_COLUMNS + PROJECT_COLUMNS
RETURN_TOLERANCE = Decimal("1e-10")
checksum = gsci_daily.checksum


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--end-date", default=date.today().isoformat(), help="Inclusive end date YYYY-MM-DD.")
    parser.add_argument("--root", default=".", help="Project root directory.")
    parser.add_argument("--migrate-gsci", action="store_true", help="Replace GSCI and preserve all later returns; no Yahoo requests.")
    parser.add_argument("--refresh-historical-sources", action="store_true", help="Try to refetch BCOM/IRX; retain valid caches on failure.")
    return parser.parse_args()


def unix_seconds(day: date) -> int:
    return int(datetime.combine(day, time.min, tzinfo=timezone.utc).timestamp())


def fetch_chart(symbol: str, end_date: date, start_date: date = START_DATE) -> dict:
    url = (
        f"https://query1.finance.yahoo.com/v8/finance/chart/{symbol}"
        f"?period1={unix_seconds(start_date)}&period2={unix_seconds(end_date + timedelta(days=1))}"
        "&interval=1d&events=history&includeAdjustedClose=true"
    )
    response = requests.get(url, timeout=60, headers={"User-Agent": "Mozilla/5.0"})
    response.raise_for_status()
    payload = response.json()
    error = payload.get("chart", {}).get("error")
    if error:
        raise RuntimeError(f"Yahoo chart error for {symbol}: {error}")
    return payload


def chart_rows(payload: dict) -> list[dict]:
    result = payload["chart"]["result"][0]
    quote = result["indicators"]["quote"][0]
    adjusted = result.get("indicators", {}).get("adjclose", [{}])[0].get("adjclose", [])
    meta = result.get("meta", {})
    try:
        exchange_tz = ZoneInfo(meta.get("exchangeTimezoneName", "America/New_York"))
    except ZoneInfoNotFoundError:
        exchange_tz = timezone(timedelta(seconds=int(meta.get("gmtoffset", 0))))
    rows = []
    for index, timestamp in enumerate(result.get("timestamp") or []):
        close = quote.get("close", [None])[index]
        if close is None:
            continue
        adj = adjusted[index] if index < len(adjusted) else close
        rows.append({"Date": datetime.fromtimestamp(timestamp, exchange_tz).date().isoformat(),
                     "Close": float(close), "Adj Close": float(close if adj is None else adj)})
    return rows


def validate_historical_chart(payload: dict, symbol: str) -> None:
    stem, first, last, minimum = HISTORICAL_CHARTS[symbol]
    actual = payload["chart"]["result"][0].get("meta", {}).get("symbol")
    if actual != symbol:
        raise ValueError(f"{stem} chart symbol is {actual!r}, expected {symbol!r}")
    rows = [row for row in chart_rows(payload) if first <= row["Date"] <= last]
    dates = [row["Date"] for row in rows]
    if first not in dates or last not in dates or len(dates) < minimum:
        raise ValueError(f"{symbol} chart lacks required {first} to {last} history ({len(dates)} rows; need {minimum})")
    if dates != sorted(set(dates)):
        raise ValueError(f"{symbol} historical dates are duplicated or unsorted")
    if any(not math.isfinite(row["Close"]) or row["Close"] <= 0 for row in rows):
        raise ValueError(f"{symbol} historical closes must be finite and positive")
    if any((date.fromisoformat(day) - date.fromisoformat(prior)).days > 10 for prior, day in zip(dates, dates[1:])):
        raise ValueError(f"{symbol} historical chart has a gap longer than 10 calendar days")


def load_historical_chart(raw_dir: Path, symbol: str, end_date: date, refresh: bool = False) -> tuple[dict, str]:
    path = raw_dir / f"{ASSET_ID}_yahoo_{HISTORICAL_CHARTS[symbol][0]}_chart.json"
    cached, cache_error = None, None
    if path.exists():
        try:
            cached = json.loads(path.read_text(encoding="utf-8"))
            validate_historical_chart(cached, symbol)
        except (ValueError, KeyError, IndexError, TypeError) as exc:
            cached, cache_error = None, exc
    if cached is not None and not refresh:
        print(f"Using validated historical {symbol} cache: {path}")
        return cached, "cached"
    try:
        payload = fetch_chart(symbol, end_date, start_date=date.fromisoformat(GSCI_END))
        validate_historical_chart(payload, symbol)
    except (requests.RequestException, RuntimeError, ValueError, KeyError, IndexError, TypeError) as exc:
        if cached is not None:
            print(f"Historical {symbol} refresh unavailable ({exc}); retaining validated cache")
            return cached, "cached_after_fetch_error"
        detail = f"; cached chart invalid: {cache_error}" if cache_error else ""
        raise RuntimeError(f"Historical {symbol} unavailable and no valid cache at {path}{detail}") from exc
    path.write_text(json.dumps(payload), encoding="utf-8")
    return payload, "fetched"


def round_float(value: float | Decimal) -> str:
    rounded = f"{value:.10f}".rstrip("0").rstrip(".")
    return "0" if rounded == "-0" else rounded


def make_row(day: str, close: Decimal, adjusted: Decimal, price_return: Decimal | None,
             total_return: Decimal | None, flag: str, source: str, notes: str) -> dict[str, str]:
    return {"Date": day, "Open": "", "High": "", "Low": "", "Close": round_float(close),
            "Adj Close": round_float(adjusted), "Volume": "",
            "Price Return": "" if price_return is None else round_float(price_return),
            "Total Return": "" if total_return is None else round_float(total_return),
            "Source": source, "Quality Flag": flag, "Source Notes": notes}


def gsci_rows(source_rows: list[dict], calendar: list[str]) -> list[dict[str, str]]:
    """Sample levels first, so skipped dates' returns are included in the next row."""
    if (not calendar or calendar != sorted(set(calendar)) or calendar[0] != gsci_daily.FIRST_DATE
            or calendar[-1] != GSCI_END):
        raise ValueError("GSCI calendar must be ordered, unique and cover both endpoints")
    dates = [row["Date"] for row in source_rows]
    if dates != sorted(set(dates)):
        raise ValueError("GSCI source dates must be ordered and unique")
    source = {row["Date"]: row for row in source_rows}
    missing = set(calendar) - source.keys()
    if missing:
        raise ValueError(f"GSCI source missing selected dates: {sorted(missing)[:5]}")
    base_er, base_tr = (Decimal(str(source[calendar[0]][key])) for key in ("GSCI_ER", "GSCI_TR"))
    if not base_er.is_finite() or not base_tr.is_finite() or min(base_er, base_tr) <= 0:
        raise ValueError("GSCI base levels must be finite and positive")
    rows = []
    previous = None
    for day in calendar:
        er, tr = (Decimal(str(source[day][key])) for key in ("GSCI_ER", "GSCI_TR"))
        if not er.is_finite() or not tr.is_finite() or min(er, tr) <= 0:
            raise ValueError(f"GSCI ER/TR must be finite and positive on {day}")
        er, tr = 100 * er / base_er, 100 * tr / base_tr
        price = None if previous is None else er / previous[0] - 1
        total = None if previous is None else tr / previous[1] - 1
        rows.append(make_row(day, er, tr, price, total, GSCI_FLAG, GSCI_SOURCE, GSCI_NOTES))
        previous = er, tr
    return rows


def validate_rows(rows: list[dict[str, str]]) -> None:
    if not rows or rows[0]["Date"] != gsci_daily.FIRST_DATE:
        raise ValueError("CMDTY must begin on 1970-01-02")
    dates = [row["Date"] for row in rows]
    if dates != sorted(set(dates)):
        raise ValueError("CMDTY dates must be ordered and unique")
    previous = None
    for row in rows:
        date.fromisoformat(row["Date"])
        levels = [Decimal(row[column]) for column in ("Close", "Adj Close")]
        if any(not value.is_finite() or value <= 0 for value in levels):
            raise ValueError(f"CMDTY levels must be finite and positive on {row['Date']}")
        if previous is None:
            if levels != [Decimal(100), Decimal(100)] or row["Price Return"] or row["Total Return"]:
                raise ValueError("CMDTY must normalize both levels to 100, with blank first returns")
        else:
            for index, column in enumerate(("Price Return", "Total Return")):
                value = Decimal(row[column])
                if not value.is_finite() or abs(value - (levels[index] / previous[index] - 1)) > RETURN_TOLERANCE:
                    raise ValueError(f"CMDTY {column} fails arithmetic on {row['Date']}")
        previous = levels


def build_normalized_rows(gsci_raw: list[dict], bcom_raw: list[dict], dbc_raw: list[dict],
                          irx_raw: list[dict], calendar: list[str]) -> list[dict[str, str]]:
    rows = gsci_rows(gsci_raw, calendar)
    bcom = {row["Date"]: Decimal(str(row["Close"])) for row in bcom_raw}
    dbc = {row["Date"]: row for row in dbc_raw}
    irx = {row["Date"]: Decimal(str(row["Close"])) for row in irx_raw if row.get("Close") is not None}
    irx_dates = sorted(irx)
    if not irx_dates or irx_dates[0] > GSCI_END:
        raise ValueError("IRX must cover the GSCI/BCOM overlap; no assumed collateral rate")
    for mapping in (bcom, irx):
        if any(not value.is_finite() or value <= 0 for value in mapping.values()):
            raise ValueError("BCOM/IRX source values must be finite and positive")
    bcom_dates = sorted(day for day in bcom if GSCI_END < day <= DBC_OVERLAP)
    dbc_dates = sorted(day for day in dbc if day >= DBC_FIRST_RETURN)
    if not bcom_dates or bcom_dates[0] != BCOM_FIRST_RETURN or bcom_dates[-1] != DBC_OVERLAP or GSCI_END not in bcom:
        raise ValueError("BCOM must cover both splice overlaps and the 1991-01-03 first return")
    if not dbc_dates or dbc_dates[0] != DBC_FIRST_RETURN or DBC_OVERLAP not in dbc:
        raise ValueError("DBC must cover the 2006-02-06 overlap and 2006-02-07 first return")
    close, adjusted = Decimal(rows[-1]["Close"]), Decimal(rows[-1]["Adj Close"])
    prior_day = GSCI_END
    for day in bcom_dates:
        ratio = bcom[day] / bcom[prior_day]
        rate = irx[irx_dates[bisect.bisect_right(irx_dates, day) - 1]]
        # Preserve the existing per-observation collateral convention in this segment.
        price, total = ratio - 1, ratio * (1 + rate / 100 / 365) - 1
        close, adjusted = close * (1 + price), adjusted * (1 + total)
        rows.append(make_row(day, close, adjusted, price, total, BCOM_FLAG,
                             "Yahoo Finance chart API (^BCOM excess return, ^IRX T-bill collateral)", BCOM_NOTES))
        prior_day = day
    for day in dbc_dates:
        current = [Decimal(str(dbc[day][key])) for key in ("Close", "Adj Close")]
        prior = [Decimal(str(dbc[prior_day][key])) for key in ("Close", "Adj Close")]
        if any(not value.is_finite() or value <= 0 for value in current + prior):
            raise ValueError("DBC source values must be finite and positive")
        price, total = current[0] / prior[0] - 1, current[1] / prior[1] - 1
        close, adjusted = close * (1 + price), adjusted * (1 + total)
        rows.append(make_row(day, close, adjusted, price, total, DBC_FLAG,
                             "Yahoo Finance chart API (DBC adjusted close)", DBC_NOTES))
        prior_day = day
    validate_rows(rows)
    return rows


def replace_gsci_prefix(baseline: list[dict[str, str]], source: list[dict], calendar: list[str]) -> tuple[list[dict[str, str]], dict]:
    validate_rows(baseline)
    prefix = [row for row in baseline if row["Date"] <= GSCI_END]
    tail = [row for row in baseline if row["Date"] > GSCI_END]
    if [row["Date"] for row in prefix] != calendar:
        raise ValueError("CMDTY historical dates differ from the preserved GSCI calendar")
    if any(row["Quality Flag"] not in LEGACY_GSCI_FLAGS | {GSCI_FLAG} for row in prefix):
        raise ValueError("Unexpected source in the existing GSCI prefix")
    if not tail or tail[0]["Date"] != BCOM_FIRST_RETURN or tail[0]["Quality Flag"] != BCOM_FLAG:
        raise ValueError("Existing CMDTY lacks the 1991-01-03 BCOM splice")
    bcom_tail = [row for row in tail if row["Date"] < DBC_FIRST_RETURN]
    dbc_tail = [row for row in tail if row["Date"] >= DBC_FIRST_RETURN]
    if (not bcom_tail or bcom_tail[-1]["Date"] != DBC_OVERLAP or not dbc_tail
            or dbc_tail[0]["Date"] != DBC_FIRST_RETURN
            or any(row["Quality Flag"] != BCOM_FLAG for row in bcom_tail)
            or any(row["Quality Flag"] != DBC_FLAG for row in dbc_tail)):
        raise ValueError("Existing CMDTY lacks the expected BCOM/DBC source chain")
    rows = gsci_rows(source, calendar)
    scales = {column: Decimal(rows[-1][column]) / Decimal(prefix[-1][column]) for column in ("Close", "Adj Close")}
    for old in tail:
        row = old.copy()
        for column, scale in scales.items():
            row[column] = round_float(Decimal(old[column]) * scale)
        if row["Quality Flag"] == BCOM_FLAG:
            row["Source Notes"] = BCOM_NOTES
        rows.append(row)
    validate_rows(rows)
    if [row["Date"] for row in rows] != [row["Date"] for row in baseline]:
        raise ValueError("Migration changed the published calendar")
    max_errors = {"Close": Decimal(0), "Adj Close": Decimal(0)}
    for index in range(len(prefix), len(rows)):
        for column in max_errors:
            old_ratio = Decimal(baseline[index][column]) / Decimal(baseline[index - 1][column])
            new_ratio = Decimal(rows[index][column]) / Decimal(rows[index - 1][column])
            max_errors[column] = max(max_errors[column], abs(new_ratio - old_ratio))
    if max(max_errors.values()) > RETURN_TOLERANCE:
        raise ValueError("Migration altered later BCOM/DBC return ratios")
    splice_checks = {}
    for day in (BCOM_FIRST_RETURN, DBC_FIRST_RETURN):
        index = next(index for index, row in enumerate(rows) if row["Date"] == day)
        splice_checks[day] = {
            "prior_date": rows[index - 1]["Date"], "source_flag": rows[index]["Quality Flag"],
            **{column: {
                "baseline_return": str(Decimal(baseline[index][column]) / Decimal(baseline[index - 1][column]) - 1),
                "migrated_return": str(Decimal(rows[index][column]) / Decimal(rows[index - 1][column]) - 1),
            } for column in max_errors},
        }
    return rows, {
        "early_rows_replaced": len(prefix), "later_rows_preserved": len(tail), "calendar_unchanged": True,
        "level_scale_factors": {key: str(value) for key, value in scales.items()},
        "max_later_ratio_error": {key: str(value) for key, value in max_errors.items()},
        "later_return_columns_unchanged": all(row[key] == old[key] for row, old in zip(rows[len(prefix):], tail)
                                              for key in ("Price Return", "Total Return")),
        "splice_checks": splice_checks,
    }


def read_csv(path: Path) -> list[dict[str, str]]:
    return parse_csv(path.read_bytes())


def parse_csv(payload: bytes) -> list[dict[str, str]]:
    with io.StringIO(payload.decode("utf-8"), newline="") as handle:
        reader = csv.DictReader(handle)
        if reader.fieldnames != OUTPUT_COLUMNS:
            raise ValueError("Unexpected CMDTY output schema")
        return list(reader)


def write_csv(path: Path, rows: list[dict[str, str]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=OUTPUT_COLUMNS, lineterminator="\n")
        writer.writeheader()
        writer.writerows(rows)


def build_metadata(root: Path, rows: list[dict[str, str]], gsci_metadata: dict, raw_sources: dict,
                   migration: dict | None = None, previous_metadata: dict | None = None) -> dict:
    metadata = (previous_metadata or {}).copy()
    flags = Counter(row["Quality Flag"] for row in rows)
    metadata.update({
        "asset_id": ASSET_ID, "asset_name": ASSET_NAME, "source": SOURCE,
        "build_timestamp_utc": datetime.now(timezone.utc).isoformat(), "methodology_version": "daily_gsci_er_tr_v1",
        "row_count": len(rows), "first_date": rows[0]["Date"], "last_date": rows[-1]["Date"],
        "csv_path": "data/processed/broad_commodities.csv", "parquet_written": True,
        "quality_flags": sorted(flags), "segment_row_counts": dict(sorted(flags.items())),
        "raw_sources": {"GSCI_ER_TR": gsci_metadata, **raw_sources},
        "historical_calendar": json.loads((root / gsci_daily.CALENDAR_MANIFEST).read_text(encoding="utf-8")),
        "coverage_note": (
            "Daily GSCI ER and TR sampled on preserved CMDTY dates through 1991-01-02. "
            "Provider back-calculation before the 1991-05-01 launch; weekday holiday fills may occur. "
            "Close uses ER, Adj Close uses TR; no sparse-anchor smoothing, spot overlay or additional IRX accrual "
            "in this segment. Later BCOM plus collateral and DBC ETF definitions remain distinct."
        ),
        "redistribution_status": gsci_daily.RIGHTS,
    })
    if migration is not None:
        metadata["gsci_migration"] = migration
    return metadata


def write_outputs(root: Path, rows: list[dict[str, str]], metadata: dict, expected_old_sha256: str | None = None) -> None:
    """Validate staged CSV and Parquet before replacing any published artifact."""
    import pandas as pd

    validate_rows(rows)
    csv_path = root / "data/processed/broad_commodities.csv"
    parquet_path = csv_path.with_suffix(".parquet")
    metadata_path = root / "sources/manifests/broad_commodities_build.json"
    pending_csv, pending_parquet, pending_meta = (path.with_suffix(path.suffix + ".tmp") for path in (csv_path, parquet_path, metadata_path))
    targets = (csv_path, parquet_path, metadata_path)
    backups = {path: path.with_suffix(path.suffix + ".rollback.tmp") for path in targets}
    replaced = []
    retain_backups = False
    try:
        write_csv(pending_csv, rows)
        validate_rows(read_csv(pending_csv))
        frame = pd.read_csv(pending_csv, parse_dates=["Date"])
        frame.to_parquet(pending_parquet, index=False)
        if not frame.equals(pd.read_parquet(pending_parquet)):
            raise ValueError("CMDTY staged CSV and Parquet differ")
        metadata["csv_sha256"] = checksum(pending_csv)
        metadata["parquet_sha256"] = checksum(pending_parquet)
        metadata_path.parent.mkdir(parents=True, exist_ok=True)
        pending_meta.write_text(json.dumps(metadata, indent=2) + "\n", encoding="utf-8")
        if expected_old_sha256 is not None and checksum(csv_path) != expected_old_sha256:
            raise RuntimeError("CMDTY changed during migration; staged outputs were not applied")
        existed = {path: path.exists() for path in targets}
        for path in targets:
            if existed[path]:
                backups[path].write_bytes(path.read_bytes())
        # Finish the disposable interim copy before committing production outputs.
        write_csv(root / "data/interim/broad_commodities.csv", rows)
        if expected_old_sha256 is not None and checksum(csv_path) != expected_old_sha256:
            raise RuntimeError("CMDTY changed during staging; no production outputs were applied")
        try:
            for pending, target in zip((pending_csv, pending_parquet, pending_meta), targets):
                pending.replace(target)
                replaced.append(target)
        except BaseException as commit_error:
            retain_backups = True
            rollback_errors = []
            for target in reversed(replaced):
                try:
                    if existed[target]:
                        backups[target].replace(target)
                    else:
                        target.unlink()
                except BaseException as rollback_error:
                    rollback_errors.append(f"{target}: {rollback_error}")
            if rollback_errors:
                recovery = [str(path) for path in backups.values() if path.exists()]
                raise RuntimeError(
                    "CMDTY replacement failed and rollback is incomplete. Recovery copies retained at "
                    + ", ".join(recovery) + "; rollback errors: " + "; ".join(rollback_errors)
                ) from commit_error
            retain_backups = False
            raise
    finally:
        cleanup = (pending_csv, pending_parquet, pending_meta) + (() if retain_backups else tuple(backups.values()))
        for path in cleanup:
            path.unlink(missing_ok=True)


def versioned_baseline(root: Path, csv_path: Path, expected_sha256: str) -> dict:
    relative = csv_path.relative_to(root).as_posix()
    commit = subprocess.check_output(["git", "log", "-1", "--format=%H", "--", relative], cwd=root, text=True).strip()
    payload = subprocess.check_output(["git", "show", f"{commit}:{relative}"], cwd=root)
    if hashlib.sha256(payload).hexdigest() != expected_sha256 or checksum(csv_path) != expected_sha256:
        raise RuntimeError("CMDTY baseline changed since its input snapshot was read")
    if payload != csv_path.read_bytes():
        raise ValueError("CMDTY baseline has unversioned changes; preserve a committed baseline before migration")
    blob = subprocess.check_output(["git", "rev-parse", f"{commit}:{relative}"], cwd=root, text=True).strip()
    archive = root / "sources/raw/cmdty_baselines" / f"{expected_sha256}.csv"
    archive.parent.mkdir(parents=True, exist_ok=True)
    if archive.exists() and archive.read_bytes() != payload:
        raise ValueError("CMDTY baseline archive is corrupt")
    archive.write_bytes(payload)
    return {"csv_path": relative, "csv_sha256": expected_sha256, "git_commit": commit,
            "git_blob": blob, "local_archive": archive.relative_to(root).as_posix()}


def migrate(root: Path, source: list[dict], gsci_metadata: dict, calendar: list[str]) -> bool:
    csv_path = root / "data/processed/broad_commodities.csv"
    input_payload = csv_path.read_bytes()
    input_sha256 = hashlib.sha256(input_payload).hexdigest()
    previous = json.loads((root / "sources/manifests/broad_commodities_build.json").read_text(encoding="utf-8"))
    if previous["csv_sha256"] != input_sha256:
        raise ValueError("CMDTY build metadata does not match the input CSV snapshot")
    baseline = parse_csv(input_payload)
    rows, checks = replace_gsci_prefix(baseline, source, calendar)
    if rows == baseline:
        if previous.get("raw_sources", {}).get("GSCI_ER_TR", {}).get("sha256") != gsci_daily.SHA256:
            raise ValueError("CMDTY already uses direct levels but its source metadata is inconsistent")
        print("CMDTY already uses the verified daily GSCI ER/TR source; no outputs changed")
        return False
    version = versioned_baseline(root, csv_path, input_sha256)
    if version["csv_sha256"] != input_sha256:
        raise RuntimeError("CMDTY versioned baseline does not match the migration input snapshot")
    migration = {"timestamp_utc": datetime.now(timezone.utc).isoformat(), "baseline": version, **checks}
    raw_sources = {
        "BCOM_IRX_DBC": {"mode": "preserved_versioned_processed_return_ratios", **version,
                         "qualification": "Historical Yahoo chart caches were unavailable. Later returns were preserved, not re-fetched or re-validated against vendor feeds."}
    }
    metadata = build_metadata(root, rows, gsci_metadata, raw_sources, migration, previous)
    write_outputs(root, rows, metadata, expected_old_sha256=input_sha256)
    print(f"Migrated {checks['early_rows_replaced']} daily GSCI rows; preserved {checks['later_rows_preserved']} later return pairs")
    print(json.dumps(checks, indent=2))
    return True


def main() -> None:
    args = parse_args()
    root = Path(args.root).resolve()
    source_path, source_mode = gsci_daily.acquire(root)
    source = gsci_daily.load_snapshot(source_path)
    calendar = gsci_daily.load_calendar(root)
    gsci_metadata = gsci_daily.source_metadata(root, source_path, source_mode, source)
    if args.migrate_gsci:
        if args.refresh_historical_sources:
            raise ValueError("--migrate-gsci preserves existing returns and cannot refresh historical sources")
        migrate(root, source, gsci_metadata, calendar)
        return
    end_date = date.fromisoformat(args.end_date)
    if end_date < date.fromisoformat(DBC_FIRST_RETURN):
        raise ValueError("A full CMDTY build must include the DBC splice on 2006-02-07")
    raw_dir = root / "sources/raw"
    bcom, bcom_mode = load_historical_chart(raw_dir, BCOM_SYMBOL, end_date, args.refresh_historical_sources)
    irx, irx_mode = load_historical_chart(raw_dir, IRX_SYMBOL, end_date, args.refresh_historical_sources)
    dbc = fetch_chart(DBC_SYMBOL, end_date, start_date=date.fromisoformat(DBC_OVERLAP))
    dbc_path = raw_dir / f"{ASSET_ID}_yahoo_dbc_chart.json"
    dbc_path.write_text(json.dumps(dbc), encoding="utf-8")
    rows = build_normalized_rows(source, chart_rows(bcom), chart_rows(dbc), chart_rows(irx), calendar)
    raw_sources = {}
    for symbol, mode in ((BCOM_SYMBOL, bcom_mode), (IRX_SYMBOL, irx_mode), (DBC_SYMBOL, "fetched")):
        path = raw_dir / f"{ASSET_ID}_yahoo_{symbol.lstrip('^').lower()}_chart.json"
        raw_sources[symbol] = {"mode": mode, "path": path.relative_to(root).as_posix(), "sha256": checksum(path)}
    write_outputs(root, rows, build_metadata(root, rows, gsci_metadata, raw_sources))
    print(f"Wrote {len(rows)} CMDTY rows, {rows[0]['Date']} through {rows[-1]['Date']}")


if __name__ == "__main__":
    main()
