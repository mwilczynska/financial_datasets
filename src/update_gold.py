"""Update the Gold dataset.

GOLDPM now splices two sources whose levels compound continuously across the 2004 GLD
inception boundary (modeled spot-minus-fee before, observed GLD after). That chain cannot be
incrementally re-stitched by simply replacing a tail window, so the update path rebuilds the
full series from scratch by delegating to ``build_gold.main()`` (which refetches the LBMA PM
JSON and the GLD chart and rewrites CSV/Parquet/metadata together).
"""

from __future__ import annotations

from build_gold import main


if __name__ == "__main__":
    main()
