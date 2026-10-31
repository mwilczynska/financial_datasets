"""Build and incrementally refresh the USD cash companion datasets.

All candidates are generated and validated before published files are replaced.
The manifest is replaced last. Unchanged refreshes preserve published bytes.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import tempfile
from collections import defaultdict
from datetime import date, datetime, timedelta, timezone
from decimal import Decimal
from pathlib import Path

try:
    from .distribution_assets import ASSET_EVENT_COLUMNS, DAILY_COLUMNS, build_assets
    from .distribution_data import collect_funds, csv_bytes, normalized_numeric_rows, parquet_bytes, read_csv
    from .distribution_funds import EVENT_COLUMNS, PRICE_COLUMNS
    from .distribution_models import ASSETS, SUMMARY_COLUMNS, calibrate, calibration_summary, extend_models
    from .distribution_sources import FUNDS, ZERO_POLICY_FUNDS, SourceCache, decimal_text
    from .build_global_short_term_bonds import JST_URL, parse_jst_rows, us_weight_by_year
except ImportError:
    from distribution_assets import ASSET_EVENT_COLUMNS, DAILY_COLUMNS, build_assets
    from distribution_data import collect_funds, csv_bytes, normalized_numeric_rows, parquet_bytes, read_csv
    from distribution_funds import EVENT_COLUMNS, PRICE_COLUMNS
    from distribution_models import ASSETS, SUMMARY_COLUMNS, calibrate, calibration_summary, extend_models
    from distribution_sources import FUNDS, ZERO_POLICY_FUNDS, SourceCache, decimal_text
    from build_global_short_term_bonds import JST_URL, parse_jst_rows, us_weight_by_year

D = Decimal
ROOT = Path(__file__).resolve().parents[1]
EVENT_RECONCILIATION_DAYS = 400
FULL_RECONCILIATION_INTERVAL_DAYS = 31
MANIFEST_PATH = "sources/manifests/distributions_build.json"
OUTPUT_PATH = "data/processed/distributions"
ANNUAL_COLUMNS = ["Fund", "Year", "Distribution Contribution Sum", "Cash Event Count",
                  "Income Feature", "Income Feature Value", "Calibration Cutoff"]
COVERAGE_COLUMNS = ["Fund", "Currency", "First Quote", "Last Quote", "Cash Event Count", "Primary Event Count",
                    "Missing Payment Date Count", "Amount Conflict Count", "Routine Cash Policy", "Live Issuer Delivery"]


def digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def publication_paths() -> list[str]:
    names = [spec.stem for spec in ASSETS] + ["fund_events", "fund_prices", "asset_cash_events", "annual_calibration", "calibration_summary", "fund_coverage"]
    return [f"{OUTPUT_PATH}/{name}{suffix}" for name in names for suffix in (".csv", ".parquet")] + [
        f"{OUTPUT_PATH}/model_parameters.json", MANIFEST_PATH]


def check_current_fund_configuration() -> None:
    try:
        from .incremental_update import ASSETS as daily_sources
    except ImportError:
        from incremental_update import ASSETS as daily_sources
    current = {fund for asset in daily_sources.values() for fund in asset.symbols if not fund.startswith("^")}
    if current != set(FUNDS):
        raise ValueError("Cash source funds have drifted from the current daily updater")
    for spec in ASSETS:
        if spec.family == "modeled_leveraged":
            # Fundless 2x exposures update from ^IRX; their cash proxy must
            # itself be a current source fund.
            if not set(spec.funds) <= current:
                raise ValueError(f"{spec.alias}: cash proxy is not a current source fund")
            continue
        expected = () if spec.alias == "USLCAP" else daily_sources[spec.stem].symbols
        if spec.funds != expected:
            raise ValueError(f"{spec.alias}: cash constituents differ from the current daily updater")


def load_weights(root: Path, through_year: int, *, offline: bool) -> tuple[dict[int, D], dict]:
    cache = SourceCache(root, offline=offline)
    key = "jst_macrohistory_r6.xlsx"
    content, record = cache.get(key, JST_URL)
    weights = us_weight_by_year(parse_jst_rows(content), through_year)
    if through_year not in weights:
        raise ValueError("JST source does not supply the production blend weights")
    production_path = root / "sources/manifests/global_short_term_bonds_build.json"
    if production_path.exists():
        production = json.loads(production_path.read_text(encoding="utf-8"))["us_gdp_weight_last"]
        year = int(production["year"])
        if year in weights and abs(weights[year] - D(production["weight"])) > D("0.000000000000000000000001"):
            raise ValueError("Distribution GDP weights disagree with the production GLSTBOND weights; reconcile the same source vintage before publishing")
    cache.accept(key, content, record, first_year=min(weights), last_year=max(weights),
                 rights="JST data and derived weights retain the source non-commercial restrictions.")
    return {year: weight for year, weight in weights.items() if year >= 1970}, cache.records[key]


def merge_funds(old_events: list[dict], old_prices: list[dict], fresh_events: list[dict], fresh_prices: list[dict],
                cutoff: str, *, full: bool) -> tuple[list, list, dict]:
    previous_events = {(row["Fund"], row["Ex Date"]): row for row in old_events}
    previous_prices = {(row["Fund"], row["Date"]): row for row in old_prices}
    incoming = {(row["Fund"], row["Ex Date"]): row for row in fresh_events if full or row["Ex Date"] >= cutoff}
    events = {} if full else {key: row for key, row in previous_events.items() if key[1] < cutoff}
    retained_primary = []
    for key, row in incoming.items():
        old = previous_events.get(key)
        if old and old["Source"] != "Yahoo chart cash events":
            if row["Source"] == "Yahoo chart cash events" and old["Source"] != row["Source"]:
                precise = dict(old)
                # Keep previously verified issuer precision/dates during a
                # temporary delivery failure, using the refreshed price basis.
                if row["Previous Equivalent Price USD"]:
                    precise["Previous Equivalent Price USD"] = row["Previous Equivalent Price USD"]
                    precise["Distribution Return"] = decimal_text(D(precise["Cash USD Per Share"]) /
                                                                   D(row["Previous Equivalent Price USD"]))
                precise["Vendor Cash USD Per Share"] = row["Vendor Cash USD Per Share"]
                row = precise
                retained_primary.append({"fund": key[0], "ex_date": key[1]})
        if old and not row["Distribution Return"] and old["Distribution Return"]:
            # A delivery window's first quote has no preceding quote. It must
            # not erase a previously normalized entitlement.
            row = old
        events[key] = row
    removed = [key for key in previous_events if (full or key[1] >= cutoff) and key not in incoming]
    # A rolling issuer table can omit an older issuer-only cash event. Keep the
    # previously verified fact, explicitly audited, rather than deleting cash.
    for key in list(removed):
        old = previous_events[key]
        if old["Source"] != "Yahoo chart cash events":
            events[key] = dict(old)
            retained_primary.append({"fund": key[0], "ex_date": key[1], "reason": "issuer_only_event_absent_from_current_delivery"})
            removed.remove(key)
    if removed:
        raise ValueError(f"Distribution sources withdrew previously published cash events: {removed[:5]}; investigate before publication")
    prices = {} if full else {key: row for key, row in previous_prices.items() if key[1] < cutoff}
    for row in fresh_prices:
        key = row["Fund"], row["Date"]
        if not full and key[1] < cutoff:
            continue
        if not row["Vendor Total Return"] and key in previous_prices:
            row = previous_prices[key]
        prices[key] = dict(row)
    if set(previous_prices) - set(prices):
        raise ValueError("Distribution price refresh deleted published quote dates")
    for key, row in prices.items():
        if event := events.get(key):
            if event["Distribution Return"]:
                row["Distribution Return"] = event["Distribution Return"]
                row["Cash Status"] = event["Quality Flag"]
                if row["Quoted Price Return"]:
                    cash_return = D(row["Quoted Price Return"]) + D(row["Distribution Return"])
                    row["Cash Total Return"] = decimal_text(cash_return)
                    row["Adjustment Residual"] = decimal_text(D(row["Vendor Total Return"]) - cash_return)
    changes = []
    for key, row in events.items():
        old = previous_events.get(key)
        if old and row != old:
            changes.append({"fund": key[0], "ex_date": key[1], "old_cash_usd": old["Cash USD Per Share"],
                            "new_cash_usd": row["Cash USD Per Share"], "source": row["Source URL"]})
    return ([events[key] for key in sorted(events)], [prices[key] for key in sorted(prices)],
            {"revised_events": changes, "cached_primary_events_retained": retained_primary})


def coverage_rows(events: list[dict], prices: list[dict], deliveries: dict) -> list[dict]:
    result = []
    for fund in FUNDS:
        fund_events = [row for row in events if row["Fund"] == fund]
        fund_prices = [row for row in prices if row["Fund"] == fund]
        result.append({"Fund": fund, "Currency": "USD", "First Quote": min(row["Date"] for row in fund_prices),
                       "Last Quote": max(row["Date"] for row in fund_prices), "Cash Event Count": str(len(fund_events)),
                       "Primary Event Count": str(sum(row["Source"] != "Yahoo chart cash events" for row in fund_events)),
                       "Missing Payment Date Count": str(sum(not row["Pay Date"] for row in fund_events)),
                       "Amount Conflict Count": str(sum(row["Reconciliation"] == "issuer_vendor_amount_conflict" for row in fund_events)),
                       "Routine Cash Policy": "zero_baseline_exceptions_supported" if fund in ZERO_POLICY_FUNDS else "cash_paying",
                       "Live Issuer Delivery": deliveries[fund]["issuer_delivery"]["delivery"]})
    return result


def validate_fund_tables(events: list[dict], prices: list[dict]) -> None:
    if set(row["Fund"] for row in prices) != set(FUNDS):
        raise ValueError("Fund quote coverage does not contain the exact current source funds")
    if len({(row["Fund"], row["Ex Date"]) for row in events}) != len(events):
        raise ValueError("Duplicate normalized fund cash events")
    for row in events:
        amount = D(row["Cash USD Per Share"])
        if row["Currency"] != "USD" or row["Share Basis"] != "as_paid" or amount < 0 or not amount.is_finite():
            raise ValueError("Invalid native cash amount, currency or share basis")
        if row["Fund"] not in FUNDS:
            raise ValueError("Cash event names a fund outside the current source set")
        if row["Pay Date"] and row["Pay Date"] < row["Ex Date"]:
            raise ValueError("Unresolved contradictory payment date reached publication")
        if row["Distribution Return"] and row["Previous Equivalent Price USD"]:
            price = D(row["Previous Equivalent Price USD"])
            if price <= D("0.000000005"):
                raise ValueError("Source price is too small for the published price precision")
            expected = amount / price
            # Independently rounded fields can move in opposite directions.
            # Half a price quantum bounds |cash/P - cash/rounded(P)| exactly;
            # add half a rate quantum rather than taking their maximum.
            bound = D("0.0000000000005") + amount * D("0.000000005") / (
                price * (price - D("0.000000005")))
            if abs(expected - D(row["Distribution Return"])) > bound:
                raise ValueError(f"{row['Fund']} {row['Ex Date']}: per-fund cash does not reconcile to its source price basis")


def validate_tables(histories: dict, events: list[dict], prices: list[dict], asset_outputs: dict,
                    asset_events: list[dict], params: dict) -> None:
    validate_fund_tables(events, prices)
    if len({(row["Asset"], row["Ex Date"], row["Fund"]) for row in asset_events}) != len(asset_events):
        raise ValueError("Duplicate asset/constituent cash entitlements")
    per_day = defaultdict(lambda: D(0))
    rates = defaultdict(lambda: D(0))
    for event in asset_events:
        per_day[event["Asset"], event["Ex Date"]] += D(event["Cash USD Per Unit"])
        rates[event["Asset"], event["Ex Date"]] += D(event["Distribution Return"])
        if event["Pay Date"] and event["Modeled Pay Date"]:
            raise ValueError("An entitlement has both a verified and modeled payment date")
        if event["Cash Basis"] == "modeled" and not event["Model Version"]:
            raise ValueError("Modeled entitlement has no model version")
    for spec in ASSETS:
        rows = asset_outputs[spec.stem]
        original = histories[spec.alias]
        if [row["Date"] for row in rows] != [row["Date"] for row in original]:
            raise ValueError(f"{spec.alias}: distribution dates differ from return dates")
        for index, (row, source) in enumerate(zip(rows, original)):
            if row["Total Return"] != source["Total Return"]:
                raise ValueError(f"{spec.alias}: published total return changed in its companion")
            price = D(row["Unit Price USD"])
            if price <= 0 or not price.is_finite() or row["Currency"] != "USD" or row["Asset"] != spec.alias:
                raise ValueError(f"{spec.alias}: nonpositive or nonfinite unit value")
            if not index and (price != 100 or D(row["Cash Entitlement USD Per Unit"]) != 0):
                raise ValueError(f"{spec.alias}: invalid initial synthetic USD unit")
            if abs(per_day[spec.alias, row["Date"]] - D(row["Cash Entitlement USD Per Unit"])) > D("0.000000002"):
                raise ValueError(f"{spec.alias}: daily and event entitlements disagree")
            if abs(rates[spec.alias, row["Date"]] - D(row["Distribution Return"])) > D("0.000000000002"):
                raise ValueError(f"{spec.alias}: daily and event distribution rates disagree")
            if index:
                prior = D(rows[index - 1]["Unit Price USD"])
                total = D(row["Total Return"])
                distribution = D(row["Distribution Return"])
                residual = D(row["Return Ex Distribution Residual"])
                if abs(total - distribution - residual) > D("0.000000000002"):
                    raise ValueError(f"{spec.alias}: cash counted outside total return")
                if abs(price - prior * (1 + residual)) > max(D("0.00000003"), abs(price) * D("0.000000000003")):
                    raise ValueError(f"{spec.alias}: unit price arithmetic failed")
                pending = D(rows[index - 1]["Cash Receivable USD Per Unit"])
                expected = (pending + D(row["Cash Entitlement USD Per Unit"])
                            - D(row["Verified Cash Paid USD Per Unit"]) - D(row["Modeled Cash Paid USD Per Unit"]))
                if abs(expected - D(row["Cash Receivable USD Per Unit"])) > D("0.000000002"):
                    raise ValueError(f"{spec.alias}: payment/receivable arithmetic failed")


def run_build(root: Path, end: date, *, full: bool = False, offline: bool = False,
              refresh: bool = True, recalibrate: bool = False) -> bool:
    check_current_fund_configuration()
    root = root.resolve()
    manifest_path = root / MANIFEST_PATH
    old = json.loads(manifest_path.read_text(encoding="utf-8")) if manifest_path.exists() else {}
    today = datetime.now(timezone.utc).date()
    last_full = date.fromisoformat(old["last_full_source_check"]) if old else None
    # A newly added source fund needs its complete quote and cash history.
    new_funds = set(FUNDS) - set(old.get("latest_sources", {}).get("funds", {})) if old else set()
    full = full or not old or bool(new_funds) or (today - last_full).days >= FULL_RECONCILIATION_INTERVAL_DAYS
    if old and end.isoformat() < old["requested_end_date"]:
        raise ValueError("An incremental distribution build cannot truncate published history")
    histories = {spec.alias: [row for row in read_csv(root / f"data/processed/{spec.stem}.csv")
                              if row["Date"] <= end.isoformat()] for spec in ASSETS}
    if any(not rows for rows in histories.values()):
        raise ValueError("Every investable return history is required")
    input_hashes = {spec.stem: digest(root / f"data/processed/{spec.stem}.csv") for spec in ASSETS}
    cutoff = end - timedelta(days=EVENT_RECONCILIATION_DAYS)
    start = date(1970, 1, 1) if full else cutoff - timedelta(days=7)
    print(f"Distributions: {'full' if full else 'incremental'} source reconciliation through {end}", flush=True)
    fresh_events, fresh_prices, sources = collect_funds(root, end, start=start, full=full, refresh=refresh, offline=offline)
    folder = root / OUTPUT_PATH
    old_events = read_csv(folder / "fund_events.csv") if old else []
    old_prices = read_csv(folder / "fund_prices.csv") if old else []
    events, prices, revision = merge_funds(old_events, old_prices, fresh_events, fresh_prices, cutoff.isoformat(), full=full)
    events, prices = normalized_numeric_rows(events), normalized_numeric_rows(prices)
    weights, weight_source = load_weights(root, end.year, offline=offline)
    if old and not recalibrate:
        params = old["model_parameters"]
        fresh, annual = calibrate(histories, events, prices, params["calibration_cutoff"])
        added = [fund for fund in FUNDS if fund not in params["fund_models"]]
        if added:
            params = extend_models(params, fresh, added)
    else:
        params, annual = calibrate(histories, events, prices, date(end.year - 1, 12, 31).isoformat())
    asset_outputs, asset_events, audit = build_assets(histories, events, prices, params, weights)
    asset_outputs = {stem: normalized_numeric_rows(rows) for stem, rows in asset_outputs.items()}
    asset_events = normalized_numeric_rows(asset_events)
    validate_tables(histories, events, prices, asset_outputs, asset_events, params)
    tables = {stem: (DAILY_COLUMNS, rows) for stem, rows in asset_outputs.items()}
    tables.update({"fund_events": (EVENT_COLUMNS, events), "fund_prices": (PRICE_COLUMNS, prices),
                   "asset_cash_events": (ASSET_EVENT_COLUMNS, asset_events),
                   "annual_calibration": (ANNUAL_COLUMNS, normalized_numeric_rows(annual)),
                   "calibration_summary": (SUMMARY_COLUMNS, calibration_summary(annual, events, prices, params["calibration_cutoff"])),
                   "fund_coverage": (COVERAGE_COLUMNS, coverage_rows(events, prices, sources["funds"]))})
    payloads, artifacts = {}, {}
    for name, (columns, rows) in tables.items():
        for suffix, content in ((".csv", csv_bytes(columns, rows)), (".parquet", parquet_bytes(columns, rows))):
            relative = f"{OUTPUT_PATH}/{name}{suffix}"
            payloads[relative] = content
            artifacts[relative] = {"sha256": hashlib.sha256(content).hexdigest(), "row_count": len(rows)}
    relative = f"{OUTPUT_PATH}/model_parameters.json"
    payloads[relative] = (json.dumps(params, indent=2, sort_keys=True) + "\n").encode()
    artifacts[relative] = {"sha256": hashlib.sha256(payloads[relative]).hexdigest()}
    historical_check_advanced = full and old.get("last_full_source_check") != today.isoformat()
    if (old.get("artifacts") == artifacts and old.get("input_return_sha256") == input_hashes
            and old.get("requested_end_date") == end.isoformat() and not historical_check_advanced):
        print("Distributions unchanged; published files and manifest preserved.", flush=True)
        return False
    metadata = {"schema_version": 1, "requested_end_date": end.isoformat(),
                "reconciliation_days": EVENT_RECONCILIATION_DAYS,
                "full_reconciliation_interval_days": FULL_RECONCILIATION_INTERVAL_DAYS,
                "last_full_source_check": today.isoformat() if full else old["last_full_source_check"],
                "full_reconciliation": full, "model_parameters": params,
                "input_return_sha256": input_hashes, "artifacts": artifacts,
                "latest_sources": sources, "weight_source": weight_source,
                "us_gdp_weights": {str(year): str(value) for year, value in weights.items()},
                "full_sources": sources if full else old.get("full_sources", {}),
                "revision_audit": revision, "audit": audit,
                "rights": "Third-party source restrictions remain; code license does not license upstream data."}
    payloads[MANIFEST_PATH] = (json.dumps(metadata, indent=2, sort_keys=True) + "\n").encode()
    interim = root / "data/interim"
    interim.mkdir(parents=True, exist_ok=True)
    if not interim.resolve().is_relative_to(root):
        raise ValueError("Candidate directory is outside the intended workspace")
    with tempfile.TemporaryDirectory(prefix="distribution-build-", dir=interim) as directory:
        candidate = Path(directory).resolve()
        if not candidate.is_relative_to(interim.resolve()):
            raise ValueError("Invalid candidate directory")
        for relative, content in payloads.items():
            path = candidate / relative
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(content)
        if input_hashes != {spec.stem: digest(root / f"data/processed/{spec.stem}.csv") for spec in ASSETS}:
            raise ValueError("Existing return inputs changed while preparing distribution candidates")
        # All candidate arithmetic was checked above. Publish the manifest last,
        # so an interrupted file replacement cannot pass the hash publication gate.
        for relative in [key for key in payloads if key != MANIFEST_PATH] + [MANIFEST_PATH]:
            target = root / relative
            target.parent.mkdir(parents=True, exist_ok=True)
            if target.exists() and target.read_bytes() == payloads[relative]:
                continue
            os.replace(candidate / relative, target)
    if input_hashes != {spec.stem: digest(root / f"data/processed/{spec.stem}.csv") for spec in ASSETS}:
        raise ValueError("Existing return inputs changed during distribution publication")
    print(f"Published {len(asset_outputs)} asset series, {len(events)} fund events and {len(asset_events)} cash entitlements.", flush=True)
    return True


def cli(*, full_default: bool) -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=ROOT)
    parser.add_argument("--end-date", type=date.fromisoformat, required=True)
    parser.add_argument("--full-history", action="store_true", help="Reconcile all source histories, retaining frozen model parameters.")
    parser.add_argument("--offline", action="store_true", help="Require validated local source caches; make no network requests.")
    parser.add_argument("--recalibrate", action="store_true", help="Deliberately refit historical payout models; may revise modeled companion history.")
    args = parser.parse_args()
    run_build(args.root, args.end_date, full=full_default or args.full_history,
              offline=args.offline, refresh=not args.offline, recalibrate=args.recalibrate)
