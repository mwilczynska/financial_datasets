"""Update every processed dataset in dependency order.

This orchestrator delegates to the per-dataset update scripts so each source chain keeps
its own build logic, raw-source caching, metadata writing, and CSV/Parquet synchronization.
By default it requests data through today's date, then runs the validation suite after all
updates succeed.

Examples:
    python src/update_all_datasets.py
    python src/update_all_datasets.py --end-date 2026-06-30
    python src/update_all_datasets.py --dry-run --no-tests
    python src/update_all_datasets.py --only USLCAP GOLDPM GOLD2X
    python src/update_all_datasets.py --refresh-static-sources
"""

from __future__ import annotations

import argparse
import csv
import os
import subprocess
import sys
import time
from dataclasses import dataclass
from datetime import date
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_VALIDATION_ARGS = ("-m", "pytest", "-q", "tests/validation")


@dataclass(frozen=True)
class DatasetTask:
    key: str
    alias: str
    output_stem: str
    update_script: str
    dependencies: tuple[str, ...] = ()
    accepts_overlap_days: bool = False
    accepts_refresh_static_sources: bool = False

    @property
    def script_path(self) -> Path:
        return Path("src") / self.update_script

    @property
    def tokens(self) -> set[str]:
        return {
            self.key.lower(),
            self.alias.lower(),
            self.output_stem.lower(),
            Path(self.update_script).stem.lower(),
        }


@dataclass(frozen=True)
class TaskResult:
    task: DatasetTask
    status: str
    seconds: float
    rows: int | None = None
    first_date: str | None = None
    last_date: str | None = None


DATASET_TASKS: tuple[DatasetTask, ...] = (
    DatasetTask("us_large_cap_sp500", "USLCAP", "us_large_cap_sp500", "update_us_large_cap_sp500.py", accepts_overlap_days=True),
    DatasetTask("short_term_us_treasury", "STT", "short_term_us_treasury", "update_short_term_us_treasury.py"),
    DatasetTask("intermediate_term_us_treasury", "ITT", "intermediate_term_us_treasury", "update_intermediate_term_us_treasury.py"),
    DatasetTask("long_term_us_treasury", "LTT", "long_term_us_treasury", "update_long_term_us_treasury.py"),
    DatasetTask("gold", "GOLDPM", "gold", "update_gold.py"),
    DatasetTask("broad_commodities", "CMDTY", "broad_commodities", "update_broad_commodities.py"),
    DatasetTask("cpi_inflation", "CPI", "cpi_inflation", "update_cpi_inflation.py"),
    DatasetTask("global_stocks", "GLSTOCK", "global_stocks", "update_global_stocks.py", ("us_large_cap_sp500",)),
    DatasetTask("global_bonds", "GLBOND", "global_bonds", "update_global_bonds.py", ("intermediate_term_us_treasury",), accepts_refresh_static_sources=True),
    DatasetTask("global_short_term_bonds", "GLSTBOND", "global_short_term_bonds", "update_global_short_term_bonds.py", ("short_term_us_treasury",), accepts_refresh_static_sources=True),
    DatasetTask("us_large_cap_3x_sp500", "USLCAP3X", "us_large_cap_3x_sp500", "update_us_large_cap_3x_sp500.py", ("us_large_cap_sp500",)),
    DatasetTask("long_term_treasury_3x", "LTT3X", "long_term_us_treasury_3x", "update_long_term_treasury_3x.py", ("long_term_us_treasury",)),
    DatasetTask("intermediate_treasury_3x", "ITT3X", "intermediate_term_us_treasury_3x", "update_intermediate_treasury_3x.py", ("intermediate_term_us_treasury",)),
    DatasetTask("gold_2x", "GOLD2X", "gold_2x", "update_gold_2x.py", ("gold",)),
)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--end-date", default=date.today().isoformat(), help="Inclusive end date requested from live sources, YYYY-MM-DD.")
    parser.add_argument("--root", default=str(PROJECT_ROOT), help="Project root. Defaults to this script's parent repository.")
    parser.add_argument("--python", default=sys.executable, help="Python executable used to run child update scripts.")
    parser.add_argument("--overlap-days", type=int, default=10, help="Calendar-day overlap for the incremental USLCAP update.")
    parser.add_argument(
        "--refresh-static-sources",
        action="store_true",
        help="For GLBOND/GLSTBOND, refetch heavy historical JST/BIS/OECD/MoF/BoE sources instead of reusing cached raw files.",
    )
    parser.add_argument("--only", nargs="+", default=[], help="Only update these dataset aliases/ids/script names.")
    parser.add_argument("--skip", nargs="+", default=[], help="Skip these dataset aliases/ids/script names.")
    parser.add_argument("--allow-stale-dependencies", action="store_true", help="Allow a selected derived dataset to run without also running its base dependency.")
    parser.add_argument("--continue-on-error", action="store_true", help="Continue independent datasets after a failure. Dependents of a failed dataset are skipped.")
    parser.add_argument("--no-tests", action="store_true", help="Do not run the validation suite after successful updates.")
    parser.add_argument("--dry-run", action="store_true", help="Print the commands that would run without updating files.")
    parser.add_argument("--list-datasets", action="store_true", help="Print the update order and exit.")
    return parser.parse_args()


def validate_task_order(tasks: tuple[DatasetTask, ...]) -> None:
    seen: set[str] = set()
    for task in tasks:
        missing = [dependency for dependency in task.dependencies if dependency not in seen]
        if missing:
            raise RuntimeError(f"{task.alias} appears before dependencies: {', '.join(missing)}")
        seen.add(task.key)


def find_task(token: str) -> DatasetTask | None:
    normalized = token.lower()
    return next((task for task in DATASET_TASKS if normalized in task.tokens), None)


def resolve_tokens(tokens: list[str], label: str) -> set[str]:
    resolved: set[str] = set()
    unknown: list[str] = []
    for token in tokens:
        task = find_task(token)
        if task is None:
            unknown.append(token)
        else:
            resolved.add(task.key)
    if unknown:
        valid = ", ".join(task.alias for task in DATASET_TASKS)
        raise SystemExit(f"Unknown {label}: {', '.join(unknown)}. Valid aliases: {valid}")
    return resolved


def select_tasks(args: argparse.Namespace) -> list[DatasetTask]:
    only = resolve_tokens(args.only, "--only value")
    skip = resolve_tokens(args.skip, "--skip value")
    selected = [task for task in DATASET_TASKS if (not only or task.key in only) and task.key not in skip]
    selected_keys = {task.key for task in selected}
    stale = {
        task.alias: [dependency for dependency in task.dependencies if dependency not in selected_keys]
        for task in selected
        if any(dependency not in selected_keys for dependency in task.dependencies)
    }
    if stale and not args.allow_stale_dependencies:
        details = "; ".join(f"{alias} needs {', '.join(deps)}" for alias, deps in stale.items())
        raise SystemExit(f"Selected update set has missing dependencies: {details}. Add the dependencies or use --allow-stale-dependencies.")
    return selected


def command_for_task(task: DatasetTask, args: argparse.Namespace, root: Path) -> list[str]:
    script = root / task.script_path
    command = [
        args.python,
        str(script),
        "--end-date",
        args.end_date,
        "--root",
        str(root),
    ]
    if task.accepts_overlap_days:
        command.extend(["--overlap-days", str(args.overlap_days)])
    if task.accepts_refresh_static_sources and args.refresh_static_sources:
        command.append("--refresh-static-sources")
    return command


def format_command(command: list[str]) -> str:
    return subprocess.list2cmdline(command)


def run_command(command: list[str], root: Path, env: dict[str, str] | None = None) -> int:
    process = subprocess.Popen(
        command,
        cwd=str(root),
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
        encoding="utf-8",
        errors="replace",
        env=env,
    )
    assert process.stdout is not None
    for line in process.stdout:
        print(line.rstrip())
    return process.wait()


def csv_summary(root: Path, task: DatasetTask) -> tuple[int, str, str]:
    path = root / "data" / "processed" / f"{task.output_stem}.csv"
    if not path.exists():
        raise RuntimeError(f"Processed CSV not found: {path}")

    rows = 0
    first_date = ""
    last_date = ""
    with path.open(newline="", encoding="utf-8") as handle:
        reader = csv.DictReader(handle)
        if "Date" not in (reader.fieldnames or []):
            raise RuntimeError(f"Processed CSV has no Date column: {path}")
        for row in reader:
            rows += 1
            if not first_date:
                first_date = row["Date"]
            last_date = row["Date"]

    if rows == 0:
        raise RuntimeError(f"Processed CSV has no data rows: {path}")
    return rows, first_date, last_date


def print_dataset_list() -> None:
    print("Update order:")
    for index, task in enumerate(DATASET_TASKS, start=1):
        deps = ", ".join(task.dependencies) if task.dependencies else "-"
        print(f"{index:>2}. {task.alias:<10} {task.output_stem:<34} deps: {deps}")


def print_summary(results: list[TaskResult]) -> None:
    print("\nSummary:")
    print(f"{'Alias':<10} {'Status':<10} {'Rows':>8} {'First':<10} {'Last':<10} {'Seconds':>8}")
    for result in results:
        rows = "" if result.rows is None else str(result.rows)
        first_date = result.first_date or ""
        last_date = result.last_date or ""
        print(f"{result.task.alias:<10} {result.status:<10} {rows:>8} {first_date:<10} {last_date:<10} {result.seconds:>8.1f}")


def run_updates(args: argparse.Namespace, root: Path, tasks: list[DatasetTask]) -> int:
    env = os.environ.copy()
    env["PYTHONUNBUFFERED"] = "1"
    results: list[TaskResult] = []
    failed: set[str] = set()

    for index, task in enumerate(tasks, start=1):
        blocked_by = [dependency for dependency in task.dependencies if dependency in failed]
        if blocked_by:
            print(f"\n[{index}/{len(tasks)}] Skipping {task.alias}; failed dependency: {', '.join(blocked_by)}")
            results.append(TaskResult(task, "skipped", 0.0))
            failed.add(task.key)
            continue

        command = command_for_task(task, args, root)
        print(f"\n[{index}/{len(tasks)}] Updating {task.alias} with {task.update_script}")
        print(format_command(command))

        start = time.perf_counter()
        if args.dry_run:
            results.append(TaskResult(task, "dry-run", 0.0))
            continue

        return_code = run_command(command, root, env=env)
        seconds = time.perf_counter() - start
        if return_code != 0:
            print(f"{task.alias} failed with exit code {return_code}")
            results.append(TaskResult(task, "failed", seconds))
            failed.add(task.key)
            if not args.continue_on_error:
                print_summary(results)
                return return_code
            continue

        rows, first_date, last_date = csv_summary(root, task)
        print(f"{task.alias} updated: {rows} rows, {first_date} through {last_date}")
        results.append(TaskResult(task, "updated", seconds, rows, first_date, last_date))

    if args.dry_run:
        if not args.no_tests:
            print("\nValidation command:")
            print(format_command([args.python, *DEFAULT_VALIDATION_ARGS]))
        print_summary(results)
        return 0

    print_summary(results)

    if failed:
        print("\nOne or more updates failed; validation was not run.")
        return 1

    if args.no_tests:
        return 0

    print("\nRunning validation suite")
    test_env = os.environ.copy()
    test_env.setdefault("PYTEST_DISABLE_PLUGIN_AUTOLOAD", "1")
    test_command = [args.python, *DEFAULT_VALIDATION_ARGS]
    print(format_command(test_command))
    return run_command(test_command, root, env=test_env)


def main() -> int:
    validate_task_order(DATASET_TASKS)
    args = parse_args()
    root = Path(args.root).resolve()
    date.fromisoformat(args.end_date)

    if args.list_datasets:
        print_dataset_list()
        return 0

    tasks = select_tasks(args)
    if not tasks:
        print("No datasets selected.")
        return 0

    return run_updates(args, root, tasks)


if __name__ == "__main__":
    raise SystemExit(main())
