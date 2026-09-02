"""Update the derived 3x U.S. large-cap (UPRO-like) dataset.

This dataset is derived from the USLCAP base dataset plus live ^IRX and UPRO data, so an
incremental stitch would have to recompute the full daily-reset compounding chain anyway.
The update therefore rebuilds the whole series from the current base USLCAP CSV and freshly
fetched ^IRX / UPRO chart data by delegating to the build script's ``main()``.

Refresh the USLCAP base dataset first (``src/update_us_large_cap_sp500.py``) so the derived
3x series picks up the latest underlying total returns.
"""

from __future__ import annotations

from build_us_large_cap_3x_sp500 import main

if __name__ == "__main__":
    main()
