"""Daily orchestration must refresh companions before allowing publication."""

from types import SimpleNamespace

from src import update_all_datasets as updater
from src.distributions_pipeline import check_current_fund_configuration
from src import incremental_update
import pytest


def test_all_updater_runs_cash_after_returns_and_propagates_cash_failure(tmp_path, monkeypatch):
    manifest = tmp_path / "sources/manifests/distributions_build.json"
    manifest.parent.mkdir(parents=True)
    manifest.write_text("{}", encoding="utf-8")
    args = SimpleNamespace(python="python", end_date="2026-10-26", overlap_days=14,
                           full_rebuild=False, refresh_static_sources=False, refresh_historical_sources=False,
                           dry_run=False, no_tests=False, continue_on_error=False, skip_distributions=False)
    calls = []
    def run(command, root, env=None):
        calls.append(command)
        return 7 if any("update_distributions.py" in part for part in command) else 0
    monkeypatch.setattr(updater, "run_command", run)
    monkeypatch.setattr(updater, "csv_summary", lambda *args: (10, "2026-10-01", "2026-10-26"))
    task = next(task for task in updater.DATASET_TASKS if task.alias == "STT")
    assert updater.run_updates(args, tmp_path, [task]) == 7
    assert len(calls) == 2
    assert "update_short_term_us_treasury.py" in calls[0][1]
    assert "update_distributions.py" in calls[1][1]
    assert not any("pytest" in command for command in calls)


def test_explicit_opt_out_preserves_local_partial_update_behavior(tmp_path, monkeypatch):
    manifest = tmp_path / "sources/manifests/distributions_build.json"
    manifest.parent.mkdir(parents=True)
    manifest.write_text("{}", encoding="utf-8")
    args = SimpleNamespace(python="python", end_date="2026-10-26", overlap_days=14,
                           full_rebuild=False, refresh_static_sources=False, refresh_historical_sources=False,
                           dry_run=False, no_tests=True, continue_on_error=False, skip_distributions=True)
    calls = []
    monkeypatch.setattr(updater, "run_command", lambda command, root, env=None: calls.append(command) or 0)
    monkeypatch.setattr(updater, "csv_summary", lambda *args: (10, "2026-10-01", "2026-10-26"))
    task = next(task for task in updater.DATASET_TASKS if task.alias == "STT")
    assert updater.run_updates(args, tmp_path, [task]) == 0
    assert len(calls) == 1


def test_source_configuration_drift_stops_cash_publication(monkeypatch):
    check_current_fund_configuration()
    altered = dict(incremental_update.ASSETS)
    altered["gold"] = incremental_update.Asset("gold", "gold", ("OTHER",))
    monkeypatch.setattr(incremental_update, "ASSETS", altered)
    with pytest.raises(ValueError, match="drifted"):
        check_current_fund_configuration()
