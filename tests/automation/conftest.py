"""A skipped automation check is a failed publication check."""

from __future__ import annotations

import pytest


@pytest.hookimpl(trylast=True)
def pytest_sessionfinish(session: pytest.Session, exitstatus: int) -> None:
    reporter = session.config.pluginmanager.get_plugin("terminalreporter")
    if reporter is None:
        return
    skipped = [report for report in reporter.stats.get("skipped", [])
               if "tests/automation/" in report.nodeid.replace("\\", "/")]
    if skipped:
        reporter.write_line(f"{len(skipped)} automation check(s) skipped; publication is blocked", red=True)
        session.exitstatus = pytest.ExitCode.TESTS_FAILED
