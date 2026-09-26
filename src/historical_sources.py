"""Validated caches for sources used only before a fixed dataset splice."""

from __future__ import annotations

import json
import hashlib
import math
from datetime import date
from pathlib import Path
from typing import Callable, TypeVar


T = TypeVar("T")


def load_historical_source(
    path: Path,
    read: Callable[[Path], T],
    write: Callable[[Path, T], None],
    validate: Callable[[T], None],
    fetch: Callable[[], T],
    *,
    refresh: bool = False,
) -> tuple[T, str]:
    """Prefer a valid cache, refetch when absent, and preserve it on refresh errors."""
    cached: T | None = None
    cache_error: Exception | None = None
    if path.exists():
        try:
            cached = read(path)
            validate(cached)
        except Exception as exc:
            cached = None
            cache_error = exc

    if cached is not None and not refresh:
        print(f"Using validated historical cache: {path}")
        return cached, "cached"

    print(f"Fetching historical source: {path.name} ...")
    try:
        incoming = fetch()
        validate(incoming)
    except Exception as exc:
        if cached is not None:
            print(f"Historical refresh unavailable ({exc}); retaining validated cache: {path}")
            return cached, "cached_after_fetch_error"
        detail = f"; cached file invalid: {cache_error}" if cache_error else ""
        raise RuntimeError(f"Historical source unavailable and no valid cache at {path}{detail}") from exc

    path.parent.mkdir(parents=True, exist_ok=True)
    write(path, incoming)
    return incoming, "fetched"


def read_json(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def write_json(path: Path, payload: dict) -> None:
    path.write_text(json.dumps(payload), encoding="utf-8")


def source_record(path: Path, mode: str) -> dict[str, str]:
    """Record cache use without embedding a machine-specific absolute path."""
    return {
        "mode": mode,
        "path": f"sources/raw/{path.name}",
        "sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
    }


def validate_dated_rows(
    rows: list[dict], first_date: str, last_date: str, minimum_rows: int,
    *, value_columns: tuple[str, ...] = ("Close",), maximum_gap_days: int = 10,
) -> None:
    selected = [row for row in rows if first_date <= str(row["Date"]) <= last_date]
    dates = [str(row["Date"]) for row in selected]
    if len(dates) < minimum_rows or not dates or dates[0] != first_date or dates[-1] != last_date:
        raise ValueError(
            f"Historical cache lacks {first_date} through {last_date} "
            f"({len(dates)} rows; need at least {minimum_rows})"
        )
    if dates != sorted(set(dates)):
        raise ValueError("Historical cache dates are duplicated or unsorted")
    if any(
        (date.fromisoformat(day) - date.fromisoformat(prior)).days > maximum_gap_days
        for prior, day in zip(dates, dates[1:])
    ):
        raise ValueError(f"Historical cache has a gap longer than {maximum_gap_days} days")
    for row in selected:
        for column in value_columns:
            value = float(row[column])
            if not math.isfinite(value) or value <= 0:
                raise ValueError(f"Historical cache has invalid {column} on {row['Date']}")


def validate_yahoo_chart(
    payload: dict, symbol: str, chart_rows: Callable[[dict], list[dict]],
    first_date: str, last_date: str, minimum_rows: int,
) -> None:
    result = payload["chart"]["result"][0]
    actual_symbol = result.get("meta", {}).get("symbol")
    if actual_symbol != symbol:
        raise ValueError(f"Yahoo chart symbol is {actual_symbol!r}, expected {symbol!r}")
    validate_dated_rows(
        chart_rows(payload), first_date, last_date, minimum_rows,
        value_columns=("Close", "Adj Close"),
    )
