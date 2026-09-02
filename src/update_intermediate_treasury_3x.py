"""Update the derived 3x intermediate-term Treasury (TYD-like) dataset.

This dataset is derived from the ITT base dataset plus live ^IRX and TYD data, so an
incremental stitch would have to recompute the full daily-reset compounding chain anyway.
The update therefore rebuilds the whole series from the current base ITT CSV and freshly
fetched ^IRX / TYD chart data by delegating to the build script's ``main()``.

Refresh the ITT base dataset first (``src/update_intermediate_term_us_treasury.py``) so the
derived 3x series picks up the latest underlying total returns.
"""

from __future__ import annotations

from build_intermediate_treasury_3x import main

if __name__ == "__main__":
    main()
