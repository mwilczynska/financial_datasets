"""Shared builder for the 2x daily-reset leveraged datasets.

Six datasets follow current 2x funds. Four have a live fund:

  * ``USLCAP2X``  ProShares Ultra S&P500 (SSO)
  * ``GLSTOCK2X`` Leverage Shares 2x Long World Stock Daily ETF (WLDU, 2x VT)
  * ``ITT2X``     ProShares Ultra 7-10 Year Treasury (UST)
  * ``LTT2X``     ProShares Ultra 20+ Year Treasury (UBT)

No 2x fund exists for global bonds or short-term Treasuries, so ``GLBOND2X`` and
``STT2X`` are modeled throughout with the UST fee and calibrated UST financing
spread. They are flagged as model-derived on every row.

The daily-reset model is the one used by the 3x datasets::

    financing_daily = (IRX_t/100 + spread) * days_t / 360
    expense_daily   = expense_ratio * days_t / 365
    lev_ret_t       = 2 * u_t - 1 * financing_daily - expense_daily

``u`` is the base dataset's daily ``Total Return``. For datasets with a live
fund, the synthetic segment runs through the fund's first trading day and the
fund's adjusted-close returns are used afterward. Levels compound continuously.
``Close`` equals ``Adj Close`` and ``Price Return`` equals ``Total Return``.
"""

from __future__ import annotations

import argparse
import bisect
import csv
import hashlib
import json
from dataclasses import dataclass
from datetime import date, datetime, time, timedelta, timezone
from decimal import Decimal, getcontext
from pathlib import Path
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

import requests

getcontext().prec = 40

IRX_SYMBOL = "^IRX"
START_DATE = date(1970, 1, 1)
MAX_START_LAG_DAYS = 7
LEVERAGE = Decimal("2")
FINANCING_DAY_COUNT = Decimal("360")   # Money-market actual/360 for financing accrual.
EXPENSE_DAY_COUNT = Decimal("365")     # Actual/365 for expense accrual.

# ProShares UST parameters, reused for the two 2x exposures that have no fund.
UST_EXPENSE_RATIO = Decimal("0.0095")  # UST net expense ratio (gross 1.24%, waiver to 2027-09-30).
UST_BORROW_SPREAD = Decimal("-0.0033")  # Calibrated so the ITT model matches UST cumulative growth.

YAHOO_COLUMNS = ["Date", "Open", "High", "Low", "Close", "Adj Close", "Volume"]
PROJECT_COLUMNS = ["Price Return", "Total Return", "Source", "Quality Flag", "Source Notes"]
OUTPUT_COLUMNS = YAHOO_COLUMNS + PROJECT_COLUMNS


@dataclass(frozen=True)
class Config:
    asset_id: str
    alias: str
    base_asset_id: str
    base_alias: str
    expense_ratio: Decimal
    borrow_spread: Decimal
    fund: str | None              # Live 2x fund, or None when modeled throughout.
    fund_name: str
    fee_basis: str
    fund_fetch_start: date | None = None

    @property
    def synth_flag(self) -> str:
        style = self.fund.lower() if self.fund else "proshares_treasury_style"
        return f"model_2x_daily_reset_synthetic_from_{self.base_alias.lower()}_total_return_minus_financing_and_{style}_fee"

    @property
    def etf_flag(self) -> str | None:
        return f"observed_{self.fund.lower()}_etf_adjusted_total_return" if self.fund else None

    @property
    def synth_source(self) -> str:
        return (f"Derived 2x daily-reset model ({self.base_alias} total return; ^IRX+spread financing; "
                f"{self.fee_basis})")

    @property
    def synth_notes(self) -> str:
        target = f"observed {self.fund} history" if self.fund else "observed fund history; no 2x fund exists"
        return (f"Synthetic 2x daily-reset total-return NAV: lev_ret = 2*{self.base_alias}_total_return "
                f"- 1*(^IRX/100+{self.borrow_spread})*days/360 - {self.expense_ratio}*days/365. "
                f"Close == Adj Close. Model-derived, not {target}.")

    @property
    def etf_source(self) -> str | None:
        return f"Yahoo Finance chart API ({self.fund} adjusted-close total return)" if self.fund else None

    @property
    def etf_notes(self) -> str | None:
        if not self.fund:
            return None
        return f"Observed {self.fund} ETF adjusted-close daily total return. Close == Adj Close (normalized 2x NAV level)."


CONFIGS = {
    "us_large_cap_2x_sp500": Config(
        "us_large_cap_2x_sp500", "USLCAP2X", "us_large_cap_sp500", "USLCAP",
        expense_ratio=Decimal("0.0084"),   # SSO net expense ratio (gross 0.88%, waiver to 2027-09-30).
        borrow_spread=Decimal("0.0080"),   # Calibrated to SSO cumulative growth over 2006+.
        fund="SSO", fund_name="ProShares Ultra S&P500", fee_basis="ProShares SSO fee",
        fund_fetch_start=date(2006, 6, 1)),
    "global_stocks_2x": Config(
        "global_stocks_2x", "GLSTOCK2X", "global_stocks", "GLSTOCK",
        expense_ratio=Decimal("0.0075"),   # WLDU total expense ratio.
        borrow_spread=Decimal("0.0080"),   # SSO spread; WLDU's short history cannot calibrate its own.
        fund="WLDU", fund_name="Leverage Shares 2x Long World Stock Daily ETF",
        fee_basis="Leverage Shares WLDU fee", fund_fetch_start=date(2026, 3, 1)),
    "global_bonds_2x": Config(
        "global_bonds_2x", "GLBOND2X", "global_bonds", "GLBOND",
        expense_ratio=UST_EXPENSE_RATIO, borrow_spread=UST_BORROW_SPREAD,
        fund=None, fund_name="none (modeled with ProShares UST parameters)",
        fee_basis="ProShares UST-style fee"),
    "short_term_us_treasury_2x": Config(
        "short_term_us_treasury_2x", "STT2X", "short_term_us_treasury", "STT",
        expense_ratio=UST_EXPENSE_RATIO, borrow_spread=UST_BORROW_SPREAD,
        fund=None, fund_name="none (modeled with ProShares UST parameters)",
        fee_basis="ProShares UST-style fee"),
    "intermediate_term_us_treasury_2x": Config(
        "intermediate_term_us_treasury_2x", "ITT2X", "intermediate_term_us_treasury", "ITT",
        expense_ratio=UST_EXPENSE_RATIO, borrow_spread=UST_BORROW_SPREAD,
        fund="UST", fund_name="ProShares Ultra 7-10 Year Treasury", fee_basis="ProShares UST fee",
        fund_fetch_start=date(2010, 1, 1)),
    "long_term_us_treasury_2x": Config(
        "long_term_us_treasury_2x", "LTT2X", "long_term_us_treasury", "LTT",
        expense_ratio=Decimal("0.0095"),   # UBT net expense ratio (gross 0.98%, waiver to 2027-09-30).
        borrow_spread=Decimal("-0.0035"),  # Calibrated to UBT cumulative growth over 2010+.
        fund="UBT", fund_name="ProShares Ultra 20+ Year Treasury", fee_basis="ProShares UBT fee",
        fund_fetch_start=date(2010, 1, 1)),
}


def synthetic_return(config: Config, u: Decimal | None, irx_rate: float, delta_days: Decimal,
                     spread: Decimal | None = None) -> Decimal:
    if u is None:
        u = Decimal("0")
    spread = config.borrow_spread if spread is None else spread
    financing_daily = (Decimal(str(irx_rate)) / Decimal("100") + spread) * delta_days / FINANCING_DAY_COUNT
    expense_daily = config.expense_ratio * delta_days / EXPENSE_DAY_COUNT
    return LEVERAGE * u - (LEVERAGE - Decimal("1")) * financing_daily - expense_daily


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


def _exchange_tz(meta: dict):
    try:
        return ZoneInfo(meta.get("exchangeTimezoneName", "America/New_York"))
    except ZoneInfoNotFoundError:
        return timezone(timedelta(seconds=int(meta.get("gmtoffset", 0))))


def close_series(payload: dict, field: str = "close") -> dict[str, float]:
    """Return {date: value} from a Yahoo chart payload (close or adjclose)."""
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


def make_irx_lookup(irx_payload: dict):
    irx = close_series(irx_payload, "close")
    irx_sorted = sorted(irx)

    def get_rate(day: str) -> float:
        if day in irx:
            return irx[day]
        idx = bisect.bisect_right(irx_sorted, day) - 1
        return irx[irx_sorted[idx]] if idx >= 0 else 0.0

    return get_rate


def round_decimal(value: Decimal) -> str:
    return f"{value:.10f}".rstrip("0").rstrip(".")


def load_base_total_returns(base_csv: Path) -> list[tuple[str, Decimal | None]]:
    if not base_csv.exists():
        raise RuntimeError(f"Base dataset not found: {base_csv}. Build it first.")
    rows: list[tuple[str, Decimal | None]] = []
    with base_csv.open(newline="", encoding="utf-8") as handle:
        for row in csv.DictReader(handle):
            tr = row["Total Return"].strip()
            rows.append((row["Date"], Decimal(tr) if tr else None))
    rows.sort(key=lambda item: item[0])
    return rows


def _row(day: str, level: Decimal, ret: Decimal | str, flag: str, source: str, notes: str) -> dict[str, str]:
    level_str = round_decimal(level)
    ret_str = round_decimal(ret) if isinstance(ret, Decimal) else ret
    return {"Date": day, "Open": "", "High": "", "Low": "", "Close": level_str, "Adj Close": level_str,
            "Volume": "", "Price Return": ret_str, "Total Return": ret_str, "Source": source,
            "Quality Flag": flag, "Source Notes": notes}


def overlap_returns(config: Config, base_returns: list[tuple[str, Decimal | None]], get_irx,
                    etf_adj: dict[str, float], spread: Decimal | None = None) -> tuple[list[float], list[float]]:
    """Model and observed fund daily returns on fund trading days after inception."""
    if not etf_adj:
        return [], []
    inception = min(etf_adj)
    base_tr = dict(base_returns)
    model, observed = [], []
    previous_date: date | None = None
    prev_adj: float | None = None
    for current, _ in base_returns:
        current_date = date.fromisoformat(current)
        adj = etf_adj.get(current)
        if current >= inception and previous_date is not None and adj is not None and prev_adj is not None:
            delta = Decimal((current_date - previous_date).days)
            model.append(float(synthetic_return(config, base_tr.get(current), get_irx(current), delta, spread)))
            observed.append(adj / prev_adj - 1.0)
        previous_date = current_date
        if adj is not None:
            prev_adj = adj
    return model, observed


def calibration_stats(model: list[float], observed: list[float]) -> dict:
    n = len(model)
    if n < 2:
        return {"overlap_days": n}
    mean_m, mean_o = sum(model) / n, sum(observed) / n
    cov = sum((m - mean_m) * (o - mean_o) for m, o in zip(model, observed))
    var_m = sum((m - mean_m) ** 2 for m in model)
    var_o = sum((o - mean_o) ** 2 for o in observed)
    corr = cov / (var_m**0.5 * var_o**0.5) if var_m > 0 and var_o > 0 else None
    diffs = [m - o for m, o in zip(model, observed)]
    mean_diff = sum(diffs) / n
    daily_te = (sum((d - mean_diff) ** 2 for d in diffs) / (n - 1)) ** 0.5
    cum_model = cum_obs = 1.0
    for m, o in zip(model, observed):
        cum_model *= 1 + m
        cum_obs *= 1 + o
    return {"overlap_days": n, "daily_return_correlation": corr,
            "annualized_tracking_error": daily_te * (252**0.5), "mean_daily_return_diff": mean_diff,
            "cumulative_model_growth": cum_model, "cumulative_etf_growth": cum_obs,
            "cumulative_ratio_model_over_etf": cum_model / cum_obs if cum_obs else None}


def solve_spread(config: Config, base_returns, get_irx, etf_adj: dict[str, float]) -> Decimal:
    """Bisect the borrowing spread that equates model and fund cumulative growth."""
    low, high = Decimal("-0.02"), Decimal("0.03")
    for _ in range(40):
        middle = (low + high) / 2
        stats = calibration_stats(*overlap_returns(config, base_returns, get_irx, etf_adj, middle))
        if stats["cumulative_ratio_model_over_etf"] > 1:
            low = middle
        else:
            high = middle
    return ((low + high) / 2).quantize(Decimal("0.0001"))


def build_rows(config: Config, base_returns: list[tuple[str, Decimal | None]], irx_payload: dict,
               etf_adj: dict[str, float]) -> tuple[list[dict[str, str]], dict]:
    get_irx = make_irx_lookup(irx_payload)
    if config.fund and not etf_adj:
        raise RuntimeError(f"No {config.fund} data fetched; cannot build observed segment.")
    inception = min(etf_adj) if etf_adj else None
    base_tr = dict(base_returns)
    rows: list[dict[str, str]] = []
    level = Decimal("100")
    previous_date: date | None = None
    prev_etf_adj: float | None = None
    for current, _ in base_returns:
        current_date = date.fromisoformat(current)
        if previous_date is None:
            rows.append(_row(current, level, "", config.synth_flag, config.synth_source, config.synth_notes))
            previous_date = current_date
            prev_etf_adj = etf_adj.get(current)
            continue
        delta_days = Decimal((current_date - previous_date).days)
        adj = etf_adj.get(current)
        if inception and current > inception and adj is not None and prev_etf_adj is not None:
            lev_ret = Decimal(str(adj)) / Decimal(str(prev_etf_adj)) - Decimal("1")
            flag, source, notes = config.etf_flag, config.etf_source, config.etf_notes
        else:
            lev_ret = synthetic_return(config, base_tr.get(current), get_irx(current), delta_days)
            flag, source, notes = config.synth_flag, config.synth_source, config.synth_notes
        if lev_ret <= Decimal("-1"):
            lev_ret = Decimal("-0.9999")
        level *= Decimal("1") + lev_ret
        rows.append(_row(current, level, lev_ret, flag, source, notes))
        previous_date = current_date
        if adj is not None:
            prev_etf_adj = adj
    calibration = calibration_stats(*overlap_returns(config, base_returns, get_irx, etf_adj))
    calibration["etf_inception"] = inception
    return rows, calibration


def write_csv(path: Path, rows: list[dict[str, str]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=OUTPUT_COLUMNS, lineterminator="\n")
        writer.writeheader()
        writer.writerows(rows)


def write_parquet(csv_path: Path, parquet_path: Path) -> bool:
    try:
        import pandas as pd
        pd.read_csv(csv_path, parse_dates=["Date"]).to_parquet(parquet_path, index=False)
    except ImportError:
        return False
    return True


def checksum(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def write_build_metadata(config: Config, root: Path, rows: list[dict[str, str]], csv_path: Path,
                         parquet_written: bool, calibration: dict) -> None:
    path = root / "sources" / "manifests" / f"{config.asset_id}_build.json"
    metadata = {
        "asset_id": config.asset_id, "alias": config.alias, "base_asset_id": config.base_asset_id,
        "leverage": float(LEVERAGE), "expense_ratio": float(config.expense_ratio),
        "borrow_spread": float(config.borrow_spread), "financing_benchmark": IRX_SYMBOL,
        "observed_etf": config.fund, "reference_fund": config.fund_name,
        "build_timestamp_utc": datetime.now(timezone.utc).isoformat(),
        "row_count": len(rows), "first_date": rows[0]["Date"], "last_date": rows[-1]["Date"],
        "synthetic_rows": sum(r["Quality Flag"] == config.synth_flag for r in rows),
        "observed_etf_rows": sum(r["Quality Flag"] == config.etf_flag for r in rows),
        "csv_path": csv_path.relative_to(root).as_posix(), "csv_sha256": checksum(csv_path),
        "parquet_written": parquet_written,
        "quality_flags": sorted({row["Quality Flag"] for row in rows}),
        "calibration_vs_etf_overlap": calibration, "notes": config.synth_notes,
    }
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(metadata, indent=2, default=str) + "\n", encoding="utf-8")


def raw_paths(config: Config, root: Path) -> tuple[Path, Path | None]:
    raw = root / "sources" / "raw"
    fund = raw / f"{config.asset_id}_yahoo_{config.fund.lower()}_chart.json" if config.fund else None
    return raw / f"{config.asset_id}_yahoo_irx_chart.json", fund


def main_for(asset_id: str) -> None:
    config = CONFIGS[asset_id]
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--end-date", default=date.today().isoformat(), help="Inclusive end date, YYYY-MM-DD.")
    parser.add_argument("--root", default=".", help="Project root.")
    parser.add_argument("--calibrate", action="store_true",
                        help="Report the spread that matches fund cumulative growth; writes no outputs.")
    args = parser.parse_args()
    root = Path(args.root).resolve()
    end_date = date.fromisoformat(args.end_date)
    base_returns = load_base_total_returns(root / "data" / "processed" / f"{config.base_asset_id}.csv")

    irx_path, fund_path = raw_paths(config, root)
    irx_path.parent.mkdir(parents=True, exist_ok=True)
    print(f"Fetching {IRX_SYMBOL} ...")
    irx_payload = fetch_chart(IRX_SYMBOL, end_date)
    irx_path.write_text(json.dumps(irx_payload), encoding="utf-8")
    etf_adj: dict[str, float] = {}
    if config.fund:
        print(f"Fetching {config.fund} ...")
        etf_payload = fetch_chart(config.fund, end_date, start_date=config.fund_fetch_start)
        fund_path.write_text(json.dumps(etf_payload), encoding="utf-8")
        etf_adj = close_series(etf_payload, "adjclose")

    if args.calibrate:
        if not config.fund:
            raise SystemExit(f"{config.alias} has no live fund; it uses the UST spread.")
        spread = solve_spread(config, base_returns, make_irx_lookup(irx_payload), etf_adj)
        print(f"{config.alias}: spread matching {config.fund} cumulative growth = {spread}")
        return

    rows, calibration = build_rows(config, base_returns, irx_payload, etf_adj)
    first_date = date.fromisoformat(rows[0]["Date"])
    if first_date < START_DATE or first_date > START_DATE + timedelta(days=MAX_START_LAG_DAYS):
        raise RuntimeError(f"Dataset starts at {rows[0]['Date']}; expected near {START_DATE.isoformat()}")

    processed_csv = root / "data" / "processed" / f"{config.asset_id}.csv"
    write_csv(root / "data" / "interim" / f"{config.asset_id}.csv", rows)
    write_csv(processed_csv, rows)
    parquet_written = write_parquet(processed_csv, processed_csv.with_suffix(".parquet"))
    write_build_metadata(config, root, rows, processed_csv, parquet_written, calibration)
    synth = sum(r["Quality Flag"] == config.synth_flag for r in rows)
    print(f"Wrote {len(rows)} rows to {processed_csv} ({rows[0]['Date']} to {rows[-1]['Date']})")
    print(f"  Synthetic rows: {synth}  Observed {config.fund or '-'} rows: {len(rows) - synth}")
    print(f"  Calibration: {json.dumps(calibration, default=str)}")
