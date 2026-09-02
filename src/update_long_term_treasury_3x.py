"""Update the derived 3x long-term Treasury (TMF-like) dataset.

This dataset is derived from the LTT base dataset plus live ^IRX and TMF data, so an
incremental stitch would have to recompute the full daily-reset compounding chain anyway.
The update therefore rebuilds the whole series from the current base LTT CSV and freshly
fetched ^IRX / TMF chart data by delegating to the build script's ``main()``.

Refresh the LTT base dataset first (``src/update_long_term_us_treasury.py``) so the derived
3x series picks up the latest underlying total returns.
"""

from __future__ import annotations

from build_long_term_treasury_3x import main

if __name__ == "__main__":
    main()
