"""Verify the complete published cash contract, independently of a build run."""

from __future__ import annotations

import hashlib
import json
import subprocess
from datetime import date, datetime, timezone, timedelta
from decimal import Decimal as D
from pathlib import Path

import pyarrow.parquet as pq

try:
    from .distribution_data import read_csv
    from .distribution_models import ASSETS
    from .distribution_sources import FUNDS, parse_yahoo
    from .distributions_pipeline import (MANIFEST_PATH, OUTPUT_PATH, publication_paths,
                                         validate_tables, check_current_fund_configuration)
except ImportError:
    from distribution_data import read_csv
    from distribution_models import ASSETS
    from distribution_sources import FUNDS, parse_yahoo
    from distributions_pipeline import (MANIFEST_PATH, OUTPUT_PATH, publication_paths,
                                        validate_tables, check_current_fund_configuration)


def check_distributions(root: Path, end: date | None = None, *, sources: bool = False,
                        baseline_ref: str | None = None) -> dict:
    root = root.resolve()
    check_current_fund_configuration()
    metadata = json.loads((root / MANIFEST_PATH).read_text(encoding="utf-8"))
    requested = date.fromisoformat(metadata["requested_end_date"])
    if end and requested != end:
        raise ValueError(f"Distribution target {requested} does not match publication target {end}")
    if set(metadata["artifacts"]) != set(publication_paths()) - {MANIFEST_PATH}:
        raise ValueError("Distribution manifest does not contain the exact publication allowlist")
    tables = {}
    for relative, record in metadata["artifacts"].items():
        path = root / relative
        if hashlib.sha256(path.read_bytes()).hexdigest() != record["sha256"]:
            raise ValueError(f"Distribution artifact hash differs: {relative}")
        if path.suffix == ".csv":
            rows = read_csv(path)
            if len(rows) != record["row_count"]:
                raise ValueError(f"Distribution row count differs: {relative}")
            frame = pq.read_table(path.with_suffix(".parquet"))
            if frame.to_pylist() != rows:
                raise ValueError(f"Distribution CSV/Parquet values differ: {relative}")
            tables[path.stem] = rows
    histories = {}
    for spec in ASSETS:
        path = root / f"data/processed/{spec.stem}.csv"
        if hashlib.sha256(path.read_bytes()).hexdigest() != metadata["input_return_sha256"][spec.stem]:
            raise ValueError(f"Distribution return input changed since build: {spec.alias}")
        histories[spec.alias] = [row for row in read_csv(path) if row["Date"] <= requested.isoformat()]
        if (requested - date.fromisoformat(histories[spec.alias][-1]["Date"])).days > 5:
            raise ValueError(f"Distribution underlying asset is stale: {spec.alias}")
    params = json.loads((root / OUTPUT_PATH / "model_parameters.json").read_text(encoding="utf-8"))
    if params != metadata["model_parameters"]:
        raise ValueError("Published model parameters differ from manifest")
    validate_tables(histories, tables["fund_events"], tables["fund_prices"],
                    tables, tables["asset_cash_events"], params)
    if baseline_ref:
        check_baseline(root, baseline_ref, metadata, tables)
    if sources:
        check_live_sources(root, metadata, tables["fund_prices"], tables["fund_events"])
    return {"assets": len(ASSETS), "fund_events": len(tables["fund_events"]),
            "cash_entitlements": len(tables["asset_cash_events"]), "end_date": requested.isoformat()}


def check_baseline(root: Path, ref: str, metadata: dict, tables: dict) -> None:
    previous = subprocess.run(["git", "show", f"{ref}:{MANIFEST_PATH}"], cwd=root,
                              capture_output=True, text=True)
    if previous.returncode:
        # Initial introduction has no distribution baseline; the original
        # return-history gate still applies independently.
        return
    old = json.loads(previous.stdout)
    full = metadata["full_reconciliation"]
    cutoff = (date.fromisoformat(metadata["requested_end_date"]) -
              timedelta(days=metadata["reconciliation_days"])).isoformat()
    for spec in ASSETS:
        content = subprocess.check_output(["git", "show", f"{ref}:{OUTPUT_PATH}/{spec.stem}.csv"],
                                          cwd=root, text=True, encoding="utf-8")
        import csv
        import io
        before = list(csv.DictReader(io.StringIO(content)))
        after = {row["Date"]: row for row in tables[spec.stem]}
        if any(row["Date"] not in after for row in before):
            raise ValueError(f"Distribution history lost published dates: {spec.alias}")
        if not full and old["model_parameters"]["version"] == metadata["model_parameters"]["version"]:
            for row in before:
                if row["Date"] < cutoff and row != after[row["Date"]]:
                    raise ValueError(f"Distribution history changed outside reconciliation window: {spec.alias} {row['Date']}")


def check_live_sources(root: Path, metadata: dict, prices: list[dict], events: list[dict]) -> None:
    records = metadata["latest_sources"]["sources"]
    for record in records.values():
        if not record.get("path"):
            continue
        path = (root / record["path"]).resolve()
        if not path.is_relative_to(root / "sources"):
            raise ValueError("Distribution source object path leaves the source directory")
        if hashlib.sha256(path.read_bytes()).hexdigest() != record["sha256"]:
            raise ValueError("Distribution source object checksum differs")
    by_fund = {}
    for key, record in records.items():
        if key.startswith("yahoo_") and record.get("accepted"):
            fund = key.split("_")[1]
            by_fund[fund] = record
    if set(by_fund) != set(FUNDS):
        raise ValueError("Distribution update lacks a validated current response for every source fund")
    end = date.fromisoformat(metadata["requested_end_date"])
    event_lookup = {(row["Fund"], row["Ex Date"]): row for row in events}
    for fund, record in by_fund.items():
        retrieved = datetime.fromisoformat(record["retrieved_at_utc"]).date()
        if (datetime.now(timezone.utc).date() - retrieved).days > 5:
            raise ValueError(f"Distribution source response is not recent: {fund}")
        chart = parse_yahoo(json.loads((root / record["path"]).read_bytes()), fund, record["url"])
        scoped = [row for row in prices if row["Fund"] == fund and row["Date"] <= end.isoformat()]
        tail = scoped[-10:]
        for row in tail:
            if row["Date"] not in chart.quotes or abs(D(row["Price USD As Paid"]) - chart.as_paid_price(row["Date"])) > D("0.000000005"):
                raise ValueError(f"Distribution source price mismatch: {fund} {row['Date']}")
        if (end - date.fromisoformat(scoped[-1]["Date"])).days > 5:
            raise ValueError(f"Distribution fund quote is stale: {fund}")
        for event in chart.events:
            if scoped[0]["Date"] <= event.ex_date <= end.isoformat():
                normalized = event_lookup.get((fund, event.ex_date))
                if not normalized:
                    raise ValueError(f"Distribution source cash event omitted: {fund} {event.ex_date}")
                cash = event.amount * chart.future_split_factor(event.ex_date)
                if D(normalized["Vendor Cash USD Per Share"]) != cash:
                    raise ValueError(f"Distribution vendor cash/share basis differs: {fund} {event.ex_date}")
