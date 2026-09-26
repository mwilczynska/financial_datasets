"""Synchronize the README dataset dates with the published processed CSVs."""

from __future__ import annotations

import argparse
import csv
import sys
from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
from update_all_datasets import DATASET_TASKS  # noqa: E402


def date_bounds(path: Path) -> tuple[str, str]:
    first = last = ""
    with path.open(newline="", encoding="utf-8") as handle:
        reader = csv.DictReader(handle)
        if not reader.fieldnames or reader.fieldnames[0] != "Date":
            raise RuntimeError(f"Missing Date column: {path}")
        for row in reader:
            day = row["Date"]
            date.fromisoformat(day)
            if last and day <= last:
                raise RuntimeError(f"Unsorted or duplicate dates: {path}")
            if not first:
                first = day
            last = day
    if not first:
        raise RuntimeError(f"Empty dataset: {path}")
    return first, last


def updated_readme(root: Path) -> tuple[str, list[str]]:
    path = root / "README.md"
    lines = path.read_text(encoding="utf-8").splitlines(keepends=True)
    try:
        start = next(i for i, line in enumerate(lines) if line.strip() == "## Published datasets")
        end = next(i for i in range(start + 1, len(lines)) if lines[i].startswith("## "))
    except StopIteration as exc:
        raise RuntimeError("README published datasets section is missing") from exc
    tasks = {task.alias: task.output_stem for task in DATASET_TASKS}
    seen: set[str] = set()
    changed: list[str] = []
    for index in range(start + 1, end):
        line = lines[index]
        if not line.startswith("|"):
            continue
        cells = line.rstrip("\r\n").split("|")
        alias = cells[1].strip() if len(cells) > 1 else ""
        if alias not in tasks:
            continue
        if alias in seen or len(cells) != 9:
            raise RuntimeError(f"Duplicate or malformed README row: {alias}")
        seen.add(alias)
        stem = tasks[alias]
        for column, suffix in ((5, ".csv"), (6, ".parquet")):
            if f"data/processed/{stem}{suffix}" not in cells[column]:
                raise RuntimeError(f"README {alias} links to the wrong {suffix} output")
        first, last = date_bounds(root / "data" / "processed" / f"{stem}.csv")
        if cells[3].strip() != first or cells[4].strip() != last:
            cells[3], cells[4] = f" {first} ", f" {last} "
            newline = "\r\n" if line.endswith("\r\n") else "\n"
            lines[index] = "|".join(cells) + newline
            changed.append(alias)
    missing = tasks.keys() - seen
    if missing:
        raise RuntimeError(f"README has no published row for: {', '.join(sorted(missing))}")
    return "".join(lines), changed


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=ROOT)
    parser.add_argument("--check", action="store_true", help="Fail when README dates differ from processed CSVs")
    args = parser.parse_args()
    root = args.root.resolve()
    content, changed = updated_readme(root)
    if args.check and changed:
        raise SystemExit(f"README dates are stale for: {', '.join(changed)}")
    if changed:
        (root / "README.md").write_text(content, encoding="utf-8")
    print("README dates current" if not changed else f"README dates updated: {', '.join(changed)}")


if __name__ == "__main__":
    main()
