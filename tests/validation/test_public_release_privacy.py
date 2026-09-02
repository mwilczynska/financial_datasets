from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]


def test_public_release_tree_audit_passes() -> None:
    result = subprocess.run(
        [sys.executable, str(ROOT / "src" / "audit_public_release.py"), "--no-history"],
        cwd=ROOT,
        text=True,
        capture_output=True,
        check=False,
    )
    assert result.returncode == 0, result.stdout + result.stderr


def test_build_metadata_paths_are_repository_relative() -> None:
    manifests = sorted((ROOT / "sources" / "manifests").glob("*_build.json"))
    assert manifests

    for path in manifests:
        metadata = json.loads(path.read_text(encoding="utf-8"))
        csv_path = metadata.get("csv_path")
        assert isinstance(csv_path, str)
        assert not Path(csv_path).is_absolute()
        assert not (len(csv_path) >= 2 and csv_path[1] == ":")
        assert csv_path.replace("\\", "/").startswith("data/processed/")
