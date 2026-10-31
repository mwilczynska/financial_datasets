"""Print the explicit publication allowlist for every processed dataset."""

from __future__ import annotations

from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
from incremental_update import ASSETS  # noqa: E402
from distributions_pipeline import publication_paths  # noqa: E402

for stem in ASSETS:
    for suffix in (".csv", ".parquet"):
        print(f"data/processed/{stem}{suffix}")
    print(f"sources/manifests/{stem}_build.json")
print("README.md")
for path in publication_paths():
    print(path)
