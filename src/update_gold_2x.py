"""Update the derived 2x gold (UGL-like) dataset.

This dataset is derived from the GOLDPM base dataset plus live ^IRX and UGL data, so an
incremental stitch would have to recompute the full daily-reset compounding chain anyway.
The update therefore rebuilds the whole series from the current base GOLDPM CSV and freshly
fetched ^IRX / UGL chart data by delegating to the build script's ``main()``.

Refresh the GOLDPM base dataset first (``src/update_gold.py``) so the derived 2x series picks
up the latest underlying spot returns.
"""

from __future__ import annotations

from build_gold_2x import main

if __name__ == "__main__":
    main()
