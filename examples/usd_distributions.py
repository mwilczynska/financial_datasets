"""Load USD cash for a fund position or an unreinvested synthetic asset unit.

python examples/usd_distributions.py --fund SHY --shares 100 --start 2025-01-01 --end 2025-12-31
python examples/usd_distributions.py --asset GLBOND --investment-usd 10000 --start 2025-01-02 --end 2025-12-31
"""

from __future__ import annotations

import argparse
import csv
import json
from datetime import date
from decimal import Decimal as D
from pathlib import Path

import pyarrow.parquet as pq

ROOT = Path(__file__).resolve().parents[1]


def load(path: Path) -> list[dict[str, str]]:
    if path.suffix == ".parquet":
        return pq.read_table(path).to_pylist()
    with path.open(encoding="utf-8", newline="") as handle:
        return list(csv.DictReader(handle))


def synthetic_position(root: Path, asset: str, investment: D, start: str, end: str,
                       suffix: str = ".parquet") -> dict:
    folder = root / "data/processed/distributions"
    events = load(folder / ("asset_cash_events" + suffix))
    # Discover the asset from the data contract, so another project need not
    # import implementation modules from this repository.
    coverage = []
    for path in sorted(folder.glob("*" + suffix)):
        if path.stem in ("fund_events", "fund_prices", "asset_cash_events", "fund_coverage",
                         "annual_calibration", "calibration_summary"):
            continue
        rows = load(path)
        if rows and rows[0].get("Asset") == asset:
            coverage = rows
            break
    if not coverage:
        raise ValueError(f"Unknown asset: {asset}")
    entry = next((row for row in reversed(coverage) if row["Date"] <= start), None)
    exit_row = next((row for row in reversed(coverage) if row["Date"] <= end), None)
    if entry is None or exit_row is None:
        raise ValueError("Position dates precede the published history")
    if end > coverage[-1]["Date"]:
        raise ValueError("Position end exceeds the published history")
    units = investment / D(entry["Unit Price USD"])
    entitled = [row for row in events if row["Asset"] == asset and entry["Date"] < row["Ex Date"] <= end]
    verified = sum((D(row["Cash USD Per Unit"]) for row in entitled if row["Pay Date"] and row["Pay Date"] <= end), D(0)) * units
    modeled = sum((D(row["Cash USD Per Unit"]) for row in entitled if row["Modeled Pay Date"] and row["Modeled Pay Date"] <= end), D(0)) * units
    total = sum((D(row["Cash USD Per Unit"]) for row in entitled), D(0)) * units
    return {"asset": asset, "entry_close": entry["Date"], "valuation_close": exit_row["Date"],
            "synthetic_units": str(units), "cash_entitlement_usd": str(total),
            "cash_paid_on_verified_dates_usd": str(verified), "cash_paid_on_modeled_dates_usd": str(modeled),
            "receivable_usd": str(total - verified - modeled),
            "ending_asset_value_usd": str(units * D(exit_row["Unit Price USD"])),
            "cash_basis": sorted({row["Cash Basis"] for row in entitled}),
            "note": "Cash stays outside the unit. Verified payment dates do not turn modeled cash into observed cash."}


def fund_position(root: Path, fund: str, shares: D, start: str, end: str, suffix: str = ".parquet") -> dict:
    # The caller supplies the actual share count entitled on each ex-date.
    # This constant-share example assumes no intervening split or trade.
    folder = root / "data/processed/distributions"
    coverage = next((row for row in load(folder / ("fund_coverage" + suffix)) if row["Fund"] == fund), None)
    if not coverage or start < coverage["First Quote"] or end > coverage["Last Quote"]:
        raise ValueError("Unknown fund or position dates outside its observed quote coverage")
    if any(row["Fund"] == fund and start < row["Date"] <= end and D(row["Split Ratio"]) != 1
           for row in load(folder / ("fund_prices" + suffix))):
        raise ValueError("This period contains a split; supply actual entitled shares for each ex-date instead of using the constant-share example")
    rows = [row for row in load(folder / ("fund_events" + suffix))
            if row["Fund"] == fund and start < row["Ex Date"] <= end]
    return {"fund": fund, "entitled_shares_each_ex_date": str(shares),
            "cash_entitlement_usd": str(sum((D(row["Cash USD Per Share"]) * shares for row in rows), D(0))),
            "cash_with_verified_pay_date_usd": str(sum((D(row["Cash USD Per Share"]) * shares for row in rows if row["Pay Date"]), D(0))),
            "cash_paid_by_end_on_verified_dates_usd": str(sum((D(row["Cash USD Per Share"]) * shares for row in rows if row["Pay Date"] and row["Pay Date"] <= end), D(0))),
            "events_without_verified_pay_date": sum(not row["Pay Date"] for row in rows),
            "note": "Native as-paid USD per share. Update entitled share counts for trades and splits; missing payment dates are unknown."}


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=ROOT)
    choice = parser.add_mutually_exclusive_group(required=True)
    choice.add_argument("--fund")
    choice.add_argument("--asset")
    parser.add_argument("--shares", type=D, default=D(100))
    parser.add_argument("--investment-usd", type=D, default=D(10000))
    parser.add_argument("--start", required=True)
    parser.add_argument("--end", required=True)
    parser.add_argument("--csv", action="store_true")
    args = parser.parse_args()
    if date.fromisoformat(args.start) >= date.fromisoformat(args.end):
        parser.error("start must precede end")
    if args.shares <= 0 or args.investment_usd <= 0:
        parser.error("position must be positive")
    suffix = ".csv" if args.csv else ".parquet"
    result = (fund_position(args.root, args.fund, args.shares, args.start, args.end, suffix) if args.fund else
              synthetic_position(args.root, args.asset, args.investment_usd, args.start, args.end, suffix))
    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()
