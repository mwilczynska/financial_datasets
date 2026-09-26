"""Extend committed datasets from recent observations without rebuilding their history.

Full ``build_*.py`` programs remain the explicit historical-rebuild path. Daily
updates start from the committed processed CSV, recalculate a short overlap, and
retain every row before the overlap anchor verbatim. Raw recent responses are
kept locally for the publication gate; they are not distributed with the data.
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import math
import subprocess
import sys
from dataclasses import dataclass
from datetime import date, datetime, time, timedelta, timezone
from decimal import Decimal, getcontext
from pathlib import Path
from urllib.parse import quote

import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

try:
    from . import build_cpi_inflation as cpi_build
    from . import build_gold as gold_build
    from . import build_gold_2x as gold2x_build
    from . import build_global_short_term_bonds as glstbond_build
except ImportError:  # direct execution from src/
    import build_cpi_inflation as cpi_build
    import build_gold as gold_build
    import build_gold_2x as gold2x_build
    import build_global_short_term_bonds as glstbond_build


getcontext().prec = 40
YAHOO_COLUMNS = ["Date", "Open", "High", "Low", "Close", "Adj Close", "Volume"]
OUTPUT_COLUMNS = YAHOO_COLUMNS + ["Price Return", "Total Return", "Source", "Quality Flag", "Source Notes"]
PROJECT_ROOT = Path(__file__).resolve().parents[1]
TRANSIENT_STATUS = (429, 500, 502, 503, 504)


@dataclass(frozen=True)
class Asset:
    stem: str
    kind: str
    symbols: tuple[str, ...] = ()
    base_stem: str | None = None
    expected_flag: str | None = None
    builder: str | None = None


ASSETS = {
    "us_large_cap_sp500": Asset("us_large_cap_sp500", "uslcap", ("^GSPC", "^SP500TR"), expected_flag="observed_price_index_sp500_total_return"),
    "short_term_us_treasury": Asset("short_term_us_treasury", "price_adj", ("SHY",), expected_flag="observed_yahoo_shy_1_3_treasury_total_return"),
    "intermediate_term_us_treasury": Asset("intermediate_term_us_treasury", "price_adj", ("IEF",), expected_flag="observed_yahoo_ief_7_10_treasury_total_return"),
    "long_term_us_treasury": Asset("long_term_us_treasury", "price_adj", ("TLT",), expected_flag="observed_yahoo_tlt_20_plus_treasury_total_return"),
    "gold": Asset("gold", "gold", ("GLD",), expected_flag="observed_gld_etf_adjusted_total_return"),
    "broad_commodities": Asset("broad_commodities", "price_adj", ("DBC",), expected_flag="observed_yahoo_dbc_dblci_total_return_etf"),
    "cpi_inflation": Asset("cpi_inflation", "cpi"),
    "global_stocks": Asset("global_stocks", "adj_only", ("VT",), expected_flag="observed_vt_etf_adjusted_total_return"),
    "global_bonds": Asset("global_bonds", "global_bond", ("BND", "BWX"), expected_flag="observed_bnd_bwx_unhedged_daily_rebalanced_proxy"),
    "global_short_term_bonds": Asset("global_short_term_bonds", "global_short_bond", ("SHY", "ISHG", "BWZ"), expected_flag="observed_shy_ishg_bwz_gdp_weighted_short_govt_bond_unhedged_net_of_fee"),
    "us_large_cap_3x_sp500": Asset("us_large_cap_3x_sp500", "adj_only", ("UPRO",), "us_large_cap_sp500", "observed_upro_etf_adjusted_total_return"),
    "long_term_us_treasury_3x": Asset("long_term_us_treasury_3x", "adj_only", ("TMF",), "long_term_us_treasury", "observed_tmf_etf_adjusted_total_return", "build_long_term_treasury_3x.py"),
    "intermediate_term_us_treasury_3x": Asset("intermediate_term_us_treasury_3x", "adj_only", ("TYD",), "intermediate_term_us_treasury", "observed_tyd_etf_adjusted_total_return", "build_intermediate_treasury_3x.py"),
    "gold_2x": Asset("gold_2x", "gold2x", ("UGL",), "gold", "observed_ugl_etf_adjusted_total_return"),
}


def round_number(value: Decimal | float | int) -> str:
    result = f"{value:.10f}".rstrip("0").rstrip(".")
    return "0" if result in ("", "-0") else result


def ratio(current: float, previous: float) -> Decimal:
    if current <= 0 or previous <= 0 or not math.isfinite(current) or not math.isfinite(previous):
        raise RuntimeError("Source level must be finite and positive")
    return Decimal(str(current)) / Decimal(str(previous)) - Decimal("1")


def checksum(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def session_with_retries() -> requests.Session:
    session = requests.Session()
    retry = Retry(total=3, backoff_factor=2, status_forcelist=TRANSIENT_STATUS,
                  allowed_methods=frozenset({"GET", "POST"}), respect_retry_after_header=True)
    session.mount("https://", HTTPAdapter(max_retries=retry))
    session.headers.update({"User-Agent": "Mozilla/5.0"})
    return session


def unix_seconds(day: date) -> int:
    return int(datetime.combine(day, time.min, tzinfo=timezone.utc).timestamp())


def fetch_yahoo(session: requests.Session, symbol: str, start: date, end: date) -> dict:
    url = f"https://query1.finance.yahoo.com/v8/finance/chart/{quote(symbol, safe='')}"
    response = session.get(url, params={"period1": unix_seconds(start),
        "period2": unix_seconds(end + timedelta(days=1)), "interval": "1d",
        "events": "history", "includeAdjustedClose": "true"}, timeout=60)
    response.raise_for_status()
    payload = response.json()
    if payload.get("chart", {}).get("error"):
        raise RuntimeError(f"Yahoo {symbol}: {payload['chart']['error']}")
    result = (payload.get("chart", {}).get("result") or [None])[0]
    if not result or result.get("meta", {}).get("symbol") != symbol:
        raise RuntimeError(f"Yahoo {symbol}: missing or mismatched chart result")
    return payload


def chart_rows(payload: dict, *, require_adjusted: bool = True) -> dict[str, dict[str, float]]:
    result = payload["chart"]["result"][0]
    quote_rows = result.get("indicators", {}).get("quote") or []
    if not quote_rows:
        raise RuntimeError("Yahoo chart has no quote array")
    quote_row = quote_rows[0]
    adj_rows = result.get("indicators", {}).get("adjclose") or []
    adj = adj_rows[0].get("adjclose", []) if adj_rows else []
    rows: dict[str, dict[str, float]] = {}
    for index, timestamp in enumerate(result.get("timestamp") or []):
        day = datetime.fromtimestamp(timestamp, timezone.utc).date().isoformat()
        if day in rows:
            raise RuntimeError(f"Duplicate Yahoo chart date: {day}")
        close_values = quote_row.get("close") or []
        close = close_values[index] if index < len(close_values) else None
        if close is None:
            continue
        values: dict[str, float] = {"close": float(close)}
        for name in ("open", "high", "low", "volume"):
            source = quote_row.get(name) or []
            if index < len(source) and source[index] is not None:
                values[name] = float(source[index])
        if index < len(adj) and adj[index] is not None:
            values["adj"] = float(adj[index])
        elif require_adjusted:
            raise RuntimeError(f"Yahoo chart has no adjusted close on {day}")
        else:
            values["adj"] = values["close"]
        if any(not math.isfinite(v) for v in values.values()) or values["close"] <= 0 or values["adj"] <= 0:
            raise RuntimeError(f"Invalid Yahoo chart level on {day}")
        rows[day] = values
    if list(rows) != sorted(rows):
        raise RuntimeError("Yahoo chart dates are unsorted")
    return rows


def read_rows(path: Path) -> list[dict[str, str]]:
    if not path.is_file():
        raise RuntimeError(f"Missing committed baseline {path}; use the full builder explicitly")
    with path.open(newline="", encoding="utf-8") as handle:
        reader = csv.DictReader(handle)
        if reader.fieldnames != OUTPUT_COLUMNS:
            raise RuntimeError(f"Unexpected schema in {path}: {reader.fieldnames}")
        rows = list(reader)
    dates = [row["Date"] for row in rows]
    if not rows or dates != sorted(set(dates)):
        raise RuntimeError(f"Baseline dates are empty, unsorted, or duplicated: {path}")
    return rows


def write_rows(path: Path, rows: list[dict[str, str]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    with temporary.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=OUTPUT_COLUMNS)
        writer.writeheader()
        writer.writerows(rows)
    temporary.replace(path)


def write_parquet(csv_path: Path, parquet_path: Path) -> None:
    import pandas as pd
    frame = pd.read_csv(csv_path, parse_dates=["Date"])
    temporary = parquet_path.with_suffix(parquet_path.suffix + ".tmp")
    frame.to_parquet(temporary, index=False)
    temporary.replace(parquet_path)


def source_window(root: Path, asset: Asset, end: date, anchor: date,
                  session: requests.Session) -> tuple[dict[str, dict[str, dict[str, float]]], dict[str, dict]]:
    start = anchor - timedelta(days=14)
    windows: dict[str, dict[str, dict[str, float]]] = {}
    records: dict[str, dict] = {}
    raw_dir = root / "sources" / "raw" / "incremental"
    raw_dir.mkdir(parents=True, exist_ok=True)
    for symbol in asset.symbols:
        payload = fetch_yahoo(session, symbol, start, end)
        rows = chart_rows(payload, require_adjusted=symbol not in ("^GSPC", "^SP500TR"))
        if not rows or max(rows) < anchor.isoformat():
            raise RuntimeError(f"{asset.stem}: {symbol} returned no overlap through {anchor}")
        path = raw_dir / f"{asset.stem}_{symbol.lstrip('^').lower()}.json"
        path.write_text(json.dumps(payload), encoding="utf-8")
        records[symbol] = {"url": f"https://query1.finance.yahoo.com/v8/finance/chart/{quote(symbol, safe='')}",
                           "path": path.relative_to(root).as_posix(), "sha256": checksum(path),
                           "first_date": min(rows), "last_date": max(rows)}
        windows[symbol] = rows
    return windows, records


def preceding_value(series: dict[str, dict[str, float]], day: str, field: str) -> float:
    available = [key for key in series if key <= day and field in series[key]]
    if not available:
        raise RuntimeError(f"No {field} source anchor on or before {day}")
    return series[max(available)][field]


def new_row(day: str, close: Decimal | float, adj: Decimal | float,
            price_return: Decimal, total_return: Decimal, template: dict[str, str],
            **overrides: str) -> dict[str, str]:
    row = {key: "" for key in OUTPUT_COLUMNS}
    row.update({"Date": day, "Close": round_number(close), "Adj Close": round_number(adj),
                "Price Return": round_number(price_return), "Total Return": round_number(total_return),
                "Source": template["Source"], "Quality Flag": template["Quality Flag"],
                "Source Notes": template["Source Notes"]})
    row.update(overrides)
    return row


def build_recent_rows(asset: Asset, root: Path, anchor: dict[str, str], end: date,
                      windows: dict[str, dict[str, dict[str, float]]], metadata: dict,
                      session: requests.Session, records: dict[str, dict]) -> list[dict[str, str]]:
    anchor_day = anchor["Date"]
    close_level = Decimal(anchor["Close"])
    adj_level = Decimal(anchor["Adj Close"])
    rows: list[dict[str, str]] = []
    if asset.kind == "cpi":
        raise AssertionError("CPI uses its own revision-window builder")
    if asset.base_stem:
        base = read_rows(root / "data" / "processed" / f"{asset.base_stem}.csv")
        dates = [row["Date"] for row in base if anchor_day < row["Date"] <= end.isoformat()]
    elif asset.kind == "global_short_bond":
        dates = sorted({day for series in windows.values() for day in series if anchor_day < day <= end.isoformat()})
    else:
        primary = asset.symbols[0]
        dates = [day for day in windows[primary] if anchor_day < day <= end.isoformat()]

    if asset.kind == "gold":
        response = session.get(gold_build.LBMA_GOLD_PM_URL, timeout=60)
        response.raise_for_status()
        lbma_payload = response.json()
        spot = {item["d"]: float(item["v"][0]) for item in lbma_payload
                if item.get("v") and item["v"][0] is not None and item["d"] <= end.isoformat()}
        raw_path = root / "sources" / "raw" / "incremental" / "gold_lbma_pm.json"
        raw_path.write_text(json.dumps(lbma_payload), encoding="utf-8")
        records["LBMA_GOLD_PM"] = {"url": gold_build.LBMA_GOLD_PM_URL,
            "path": raw_path.relative_to(root).as_posix(), "sha256": checksum(raw_path),
            "first_date": min(spot), "last_date": max(spot)}

    previous_date = date.fromisoformat(anchor_day)
    previous_quotes = {symbol: preceding_value(series, anchor_day, "adj") for symbol, series in windows.items()}
    previous_closes = {symbol: preceding_value(series, anchor_day, "close") for symbol, series in windows.items()}
    for day in dates:
        template = anchor
        current_date = date.fromisoformat(day)
        if asset.kind == "uslcap":
            price = windows["^GSPC"].get(day)
            total = windows["^SP500TR"].get(day)
            if price is None or total is None:
                raise RuntimeError(f"USLCAP missing aligned index data on {day}")
            price_ret = ratio(price["close"], float(close_level))
            total_ret = ratio(total["close"], previous_closes["^SP500TR"])
            close_level = Decimal(str(price["close"]))
            adj_level *= Decimal("1") + total_ret
            row = new_row(day, close_level, adj_level, price_ret, total_ret, template,
                Open=round_number(price["open"]) if "open" in price else "",
                High=round_number(price["high"]) if "high" in price else "",
                Low=round_number(price["low"]) if "low" in price else "",
                Volume=str(int(price["volume"])) if "volume" in price else "")
        elif asset.kind in ("price_adj", "adj_only"):
            symbol = asset.symbols[0]
            quote_row = windows[symbol].get(day)
            if quote_row is None:
                raise RuntimeError(f"{asset.stem}: {symbol} missing on base date {day}")
            total_ret = ratio(quote_row["adj"], previous_quotes[symbol])
            price_ret = ratio(quote_row["close"], previous_closes[symbol]) if asset.kind == "price_adj" else total_ret
            close_level *= Decimal("1") + price_ret
            adj_level *= Decimal("1") + total_ret
            row = new_row(day, close_level, adj_level, price_ret, total_ret, template)
        elif asset.kind == "gold":
            quote_row = windows["GLD"][day]
            total_ret = ratio(quote_row["adj"], previous_quotes["GLD"])
            if day in spot:
                close_level = Decimal(str(spot[day]))
                overrides = {"Quality Flag": gold_build.ETF_FLAG, "Source": gold_build.ETF_SOURCE,
                             "Source Notes": gold_build.ETF_NOTES}
            else:
                close_level *= Decimal("1") + ratio(quote_row["adj"], previous_quotes["GLD"])
                overrides = {"Quality Flag": gold_build.ETF_FFILL_FLAG,
                    "Source": gold_build.ETF_FFILL_SOURCE, "Source Notes": gold_build.ETF_FFILL_NOTES}
            price_ret = close_level / Decimal(anchor["Close"] if not rows else rows[-1]["Close"]) - Decimal("1")
            adj_level *= Decimal("1") + total_ret
            row = new_row(day, close_level, adj_level, price_ret, total_ret, template, **overrides)
        elif asset.kind == "global_bond":
            bnd = windows["BND"].get(day)
            bwx = windows["BWX"].get(day)
            if bnd is None or bwx is None:
                raise RuntimeError(f"GLBOND missing BND/BWX on {day}")
            total_ret = Decimal("0.45") * ratio(bnd["adj"], previous_quotes["BND"]) + Decimal("0.55") * ratio(bwx["adj"], previous_quotes["BWX"])
            close_level *= Decimal("1") + total_ret
            adj_level = close_level
            row = new_row(day, close_level, adj_level, total_ret, total_ret, template)
        elif asset.kind == "global_short_bond":
            shy = windows["SHY"].get(day)
            if shy is None:
                for symbol, series in windows.items():
                    if day in series:
                        previous_quotes[symbol] = series[day]["adj"]
                        previous_closes[symbol] = series[day]["close"]
                continue
            intl = [ratio(windows[symbol][day]["adj"], previous_quotes[symbol])
                    for symbol in ("ISHG", "BWZ") if day in windows[symbol]]
            if not intl:
                for symbol, series in windows.items():
                    if day in series:
                        previous_quotes[symbol] = series[day]["adj"]
                        previous_closes[symbol] = series[day]["close"]
                continue
            weight = Decimal(metadata["us_gdp_weight_last"]["weight"])
            shy_ret = ratio(shy["adj"], previous_quotes["SHY"])
            total_ret = weight * shy_ret + (Decimal("1") - weight) * sum(intl) / Decimal(len(intl))
            elapsed = Decimal((current_date - previous_date).days)
            fee = glstbond_build.REPRESENTATIVE_FEE_ANNUAL * elapsed / Decimal("365")
            price_ret = (Decimal("1") + total_ret) / (Decimal("1") - fee) - Decimal("1")
            close_level *= Decimal("1") + price_ret
            adj_level *= Decimal("1") + total_ret
            row = new_row(day, close_level, adj_level, price_ret, total_ret, template)
        elif asset.kind == "gold2x":
            quote_row = windows["UGL"].get(day)
            if quote_row is None:
                total_ret = Decimal("0")
                overrides = {"Quality Flag": gold2x_build.HOLIDAY_FLAG,
                    "Source": gold2x_build.HOLIDAY_SOURCE, "Source Notes": gold2x_build.HOLIDAY_NOTES}
            else:
                total_ret = ratio(quote_row["adj"], previous_quotes["UGL"])
                overrides = {"Quality Flag": gold2x_build.ETF_FLAG,
                    "Source": gold2x_build.ETF_SOURCE, "Source Notes": gold2x_build.ETF_NOTES}
            close_level *= Decimal("1") + total_ret
            adj_level = close_level
            row = new_row(day, close_level, adj_level, total_ret, total_ret, template, **overrides)
        else:
            raise AssertionError(asset.kind)
        rows.append(row)
        previous_date = current_date
        for symbol, series in windows.items():
            if day in series:
                previous_quotes[symbol] = series[day]["adj"]
                previous_closes[symbol] = series[day]["close"]
    return rows


def build_cpi_recent(root: Path, existing: list[dict[str, str]], end: date,
                     session: requests.Session) -> tuple[list[dict[str, str]], dict[str, dict], str, str]:
    metadata_path = root / "sources" / "manifests" / "cpi_inflation_build.json"
    metadata = json.loads(metadata_path.read_text(encoding="utf-8"))
    previous_monthly = date.fromisoformat(metadata["latest_monthly_observation"])
    start_year = max(1970, previous_monthly.year - 1)
    payload = {"seriesid": [cpi_build.BLS_SERIES], "startyear": str(start_year), "endyear": str(end.year)}
    response = session.post(cpi_build.BLS_API_URL, json=payload, timeout=60)
    response.raise_for_status()
    body = response.json()
    if body.get("status") != "REQUEST_SUCCEEDED":
        raise RuntimeError(f"BLS recent CPI request failed: {body}")
    monthly = cpi_build.parse_bls_monthly([body])
    if not any(day == previous_monthly for day, _ in monthly):
        raise RuntimeError(f"BLS response omitted committed CPI monthly anchor {previous_monthly}")
    old_by_date = {row["Date"]: row for row in existing}
    changed = [day for day, value in monthly if day.isoformat() in old_by_date and
               old_by_date[day.isoformat()]["Quality Flag"] == cpi_build.MONTHLY_FLAG and
               abs(float(old_by_date[day.isoformat()]["Close"]) - value) > 1e-9]
    if changed and min(changed) < previous_monthly - timedelta(days=62):
        raise RuntimeError(f"BLS revised CPI outside the permitted recent window: {min(changed)}")
    new_monthly = [day for day, _ in monthly if day > previous_monthly]
    if changed or new_monthly:
        earliest = min(changed + new_monthly)
        prior = [day for day, _ in monthly if day < earliest and day.isoformat() in old_by_date]
        if not prior:
            raise RuntimeError("No committed CPI monthly anchor before the revision")
        anchor_day = max(prior).isoformat()
    else:
        anchor_day = existing[-1]["Date"]
    anchor = old_by_date[anchor_day]
    previous_level = float(anchor["Close"])
    rows = [row for row in existing if row["Date"] <= anchor_day]
    current = date.fromisoformat(anchor_day) + timedelta(days=1)
    while current <= end:
        level, flag, notes = cpi_build.daily_cpi_level(current, monthly)
        daily_return = cpi_build.round_float(level / previous_level - 1)
        rows.append({"Date": current.isoformat(), "Open": "", "High": "", "Low": "",
                     "Close": cpi_build.round_float(level), "Adj Close": cpi_build.round_float(level),
                     "Volume": "", "Price Return": daily_return, "Total Return": daily_return,
                     "Source": cpi_build.SOURCE, "Quality Flag": flag, "Source Notes": notes})
        previous_level = level
        current += timedelta(days=1)
    raw_path = root / "sources" / "raw" / "incremental" / "cpi_bls_recent.json"
    raw_path.parent.mkdir(parents=True, exist_ok=True)
    raw_path.write_text(json.dumps(body), encoding="utf-8")
    record = {"BLS_CUSR0000SA0": {"url": cpi_build.BLS_API_URL,
        "path": raw_path.relative_to(root).as_posix(), "sha256": checksum(raw_path),
        "first_date": monthly[0][0].isoformat(), "last_date": monthly[-1][0].isoformat()}}
    return rows, record, monthly[-1][0].isoformat(), anchor_day


def same_observation(old: dict[str, str], new: dict[str, str], kind: str) -> bool:
    """Ignore harmless level rounding while detecting changed source returns."""
    if any(old[key] != new[key] for key in ("Source", "Quality Flag", "Source Notes")):
        return False
    for key in ("Price Return", "Total Return"):
        if abs(float(old[key]) - float(new[key])) > 1e-9:
            return False
    if kind in ("uslcap", "gold") and abs(float(old["Close"]) - float(new["Close"])) > 1e-7:
        return False
    if kind == "uslcap" and any(old[key] != new[key] for key in ("Open", "High", "Low", "Volume")):
        return False
    return True


def update_asset(stem: str, root: Path, end: date, overlap_days: int = 14,
                 session: requests.Session | None = None) -> bool:
    asset = ASSETS[stem]
    if overlap_days < 7:
        raise ValueError("Overlap must be at least seven calendar days")
    csv_path = root / "data" / "processed" / f"{stem}.csv"
    existing = read_rows(csv_path)
    if end.isoformat() < existing[-1]["Date"]:
        raise RuntimeError(f"Requested end {end} precedes committed {stem} end {existing[-1]['Date']}")
    metadata_path = root / "sources" / "manifests" / f"{stem}_build.json"
    metadata = json.loads(metadata_path.read_text(encoding="utf-8"))
    session = session or session_with_retries()
    if asset.kind == "cpi":
        rows, records, monthly_date, anchor_day = build_cpi_recent(root, existing, end, session)
    else:
        anchor_candidates = [row for row in existing if row["Date"] < (date.fromisoformat(existing[-1]["Date"]) - timedelta(days=overlap_days)).isoformat()]
        if not anchor_candidates:
            raise RuntimeError(f"No {stem} overlap anchor; use the full builder")
        anchor = anchor_candidates[-1]
        anchor_day = anchor["Date"]
        if asset.expected_flag and anchor["Quality Flag"] != asset.expected_flag:
            # GOLDPM and GOLD2X have a second observed flag on cross-market holidays.
            permitted = {gold_build.ETF_FFILL_FLAG} if asset.kind == "gold" else ({gold2x_build.HOLIDAY_FLAG} if asset.kind == "gold2x" else set())
            if anchor["Quality Flag"] not in permitted:
                raise RuntimeError(f"{stem} is not in its documented observed segment at {anchor_day}")
        windows, records = source_window(root, asset, end, date.fromisoformat(anchor_day), session)
        recent = build_recent_rows(asset, root, anchor, end, windows, metadata, session, records)
        rows = [row for row in existing if row["Date"] <= anchor_day] + recent
        old_recent = {row["Date"] for row in existing if row["Date"] > anchor_day}
        new_recent = {row["Date"] for row in recent}
        missing = old_recent - new_recent
        if missing:
            raise RuntimeError(f"{stem} source would delete committed dates: {sorted(missing)[:5]}")
        old_by_day = {row["Date"]: row for row in existing}
        revised = [row["Date"] for row in recent if row["Date"] in old_by_day
                   and not same_observation(old_by_day[row["Date"]], row, asset.kind)]
        revised.extend(day for day in new_recent - old_recent if day <= existing[-1]["Date"])
        if revised:
            first_revised = min(revised)
            prior = [row for row in existing if row["Date"] < first_revised]
            if not prior:
                raise RuntimeError(f"{stem}: no committed anchor before revised observation")
            anchor = prior[-1]
            anchor_day = anchor["Date"]
        else:
            # An unchanged overlap is authoritative. This makes repeat runs byte-for-byte
            # stable and prevents rounding from slowly rewriting historical levels.
            anchor = existing[-1]
            anchor_day = anchor["Date"]
        rows = [row for row in existing if row["Date"] <= anchor_day]
        rows.extend(build_recent_rows(asset, root, anchor, end, windows, metadata, session, records))
        monthly_date = ""
    if rows == existing:
        print(f"{stem}: no changed observations through {end}")
        return False
    if [row["Date"] for row in rows] != sorted({row["Date"] for row in rows}):
        raise RuntimeError(f"{stem} candidate dates are unsorted or duplicated")
    write_rows(root / "data" / "interim" / f"{stem}.csv", rows)
    write_rows(csv_path, rows)
    write_parquet(csv_path, root / "data" / "processed" / f"{stem}.parquet")
    metadata.update({"row_count": len(rows), "first_date": rows[0]["Date"],
        "last_date": rows[-1]["Date"], "csv_sha256": checksum(csv_path),
        "parquet_written": True, "quality_flags": sorted({row["Quality Flag"] for row in rows}),
        "last_incremental_update_utc": datetime.now(timezone.utc).isoformat(),
        "incremental_update": {"overlap_anchor": anchor_day, "requested_end_date": end.isoformat(),
                               "recent_sources": records}})
    if monthly_date:
        metadata["latest_monthly_observation"] = monthly_date
    if asset.kind == "global_short_bond":
        # The documented JST GDP weight is carried forward after its final year.
        metadata["us_gdp_weight_last"]["year"] = date.fromisoformat(rows[-1]["Date"]).year
    metadata_path.write_text(json.dumps(metadata, indent=2) + "\n", encoding="utf-8")
    print(f"{stem}: {len(existing)} -> {len(rows)} rows, {rows[-1]['Date']} last date; overlap anchor {anchor_day}")
    return True


def main_for_asset(stem: str) -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--end-date", default=date.today().isoformat())
    parser.add_argument("--root", default=str(PROJECT_ROOT))
    parser.add_argument("--overlap-days", type=int, default=14)
    parser.add_argument("--full-rebuild", action="store_true")
    parser.add_argument("--refresh-historical-sources", action="store_true")
    parser.add_argument("--refresh-static-sources", action="store_true")
    args = parser.parse_args()
    asset = ASSETS[stem]
    if args.full_rebuild or args.refresh_historical_sources or args.refresh_static_sources:
        builder = asset.builder or f"build_{stem}.py"
        command = [sys.executable, str(Path(__file__).with_name(builder)), "--end-date", args.end_date,
                   "--root", str(Path(args.root).resolve())]
        if args.refresh_historical_sources:
            command.append("--refresh-historical-sources")
        if args.refresh_static_sources:
            command.append("--refresh-static-sources")
        raise SystemExit(subprocess.call(command))
    update_asset(stem, Path(args.root).resolve(), date.fromisoformat(args.end_date), args.overlap_days)
