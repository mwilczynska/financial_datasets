"""Deterministic USD distribution output I/O and shared source collection."""

from __future__ import annotations

import csv
import hashlib
import io
import json
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import date
from decimal import Decimal
from pathlib import Path
from typing import Any

import pyarrow as pa
import pyarrow.parquet as pq

try:
    from .distribution_funds import EVENT_COLUMNS, PRICE_COLUMNS, normalize_fund
    from .distribution_sources import (Chart, FUNDS, ZERO_POLICY_FUNDS, SourceCache, decimal_text,
                                       issuer_events, yahoo_chart)
except ImportError:
    from distribution_funds import EVENT_COLUMNS, PRICE_COLUMNS, normalize_fund
    from distribution_sources import (Chart, FUNDS, ZERO_POLICY_FUNDS, SourceCache, decimal_text,
                                      issuer_events, yahoo_chart)


def read_csv(path: Path) -> list[dict[str, str]]:
    with path.open(encoding="utf-8", newline="") as handle:
        return list(csv.DictReader(handle))


def csv_bytes(columns: list[str], rows: list[dict[str, str]]) -> bytes:
    handle = io.StringIO(newline="")
    writer = csv.DictWriter(handle, fieldnames=columns, lineterminator="\n", extrasaction="raise")
    writer.writeheader()
    writer.writerows(rows)
    return handle.getvalue().encode("utf-8")


def parquet_bytes(columns: list[str], rows: list[dict[str, str]]) -> bytes:
    """Lossless string columns preserve exact money and unknown-vs-zero values.

    CSV and Parquet deliberately have the same lexical contract. Consumer
    examples provide explicit date/numeric conversion instead of silently
    converting precise cash amounts to binary floating point.
    """
    table = pa.Table.from_arrays([pa.array([row.get(name, "") for row in rows], type=pa.string())
                                 for name in columns], names=columns)
    handle = io.BytesIO()
    pq.write_table(table, handle, compression="zstd")
    return handle.getvalue()


def normalized_numeric_rows(rows: list[dict[str, str]]) -> list[dict[str, str]]:
    result = []
    for row in rows:
        new = dict(row)
        for key, value in new.items():
            if key == "Total Return":
                continue  # Preserve the canonical asset input's lexical value.
            if value and ("Return" in key or key in ("Adjustment Residual",)):
                new[key] = decimal_text(Decimal(value).quantize(Decimal("0.000000000001")))
            elif value and ("USD Per Unit" in key or key in ("Distribution Contribution Sum", "Income Feature Value")):
                new[key] = decimal_text(Decimal(value).quantize(Decimal("0.000000000001")))
            elif value and ("Price USD" in key or key == "Previous Equivalent Price USD"):
                new[key] = decimal_text(Decimal(value).quantize(Decimal("0.00000001")))
        result.append(new)
    return result


def collect_funds(root: Path, end: date, *, start: date = date(1970, 1, 1),
                  full: bool = True, refresh: bool = True, offline: bool = False,
                  session: Any = None) -> tuple[list[dict[str, str]], list[dict[str, str]], dict]:
    cache = SourceCache(root, offline=offline, session=session)
    charts: dict[str, Chart] = {}
    # One quote/action request per unique current fund, including shared SHY.
    with ThreadPoolExecutor(max_workers=4) as pool:
        futures = {pool.submit(yahoo_chart, cache, fund, start, end, refresh=refresh): fund for fund in FUNDS}
        for future in as_completed(futures):
            fund = futures[future]
            charts[fund] = future.result()
    issuer, deliveries = issuer_events(cache, FUNDS, end, refresh=refresh, full=full)
    event_rows, price_rows, diagnostics = [], [], {}
    for fund in FUNDS:
        first_delivered_quote = min(charts[fund].quotes)
        delivered_issuer = [event for event in issuer.get(fund, []) if event.ex_date >= first_delivered_quote]
        events, prices, facts = normalize_fund(charts[fund], delivered_issuer, end.isoformat(),
                                              zero_policy=fund in ZERO_POLICY_FUNDS)
        event_rows.extend(events)
        price_rows.extend(prices)
        diagnostics[fund] = {**facts, "issuer_delivery": deliveries[fund]}
    source_manifest = {"sources": dict(sorted(cache.records.items())), "funds": diagnostics,
                       "requested_end_date": end.isoformat(), "requested_start_date": start.isoformat()}
    return (normalized_numeric_rows(sorted(event_rows, key=lambda row: (row["Fund"], row["Ex Date"]))),
            normalized_numeric_rows(sorted(price_rows, key=lambda row: (row["Fund"], row["Date"]))),
            source_manifest)


def output_digest(content: bytes) -> str:
    return hashlib.sha256(content).hexdigest()
