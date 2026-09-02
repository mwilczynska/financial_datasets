# Project Methodology

This file defines the general methodology that applies to all datasets. Dataset-specific derivations, source chains, tests, and caveats are in the individual files listed in [`docs/dataset_methodologies.md`](dataset_methodologies.md).

## Canonical Output Shape

Final datasets begin with Yahoo Finance-compatible columns:

```text
Date, Open, High, Low, Close, Adj Close, Volume
```

Followed by project-specific columns:

```text
Price Return, Total Return, Source, Quality Flag, Source Notes
```

For index-level or reconstructed datasets, OHLCV values may not exist. In that case:

- `Close` holds the best available daily price-return level.
- `Adj Close` holds a defensible total-return-adjusted level, or matches `Close` when no total-return adjustment is available.
- Missing `Open`, `High`, `Low`, or `Volume` remain blank, not fabricated.
- `Quality Flag` explains whether a row is observed, adjusted, reconstructed, estimated, incomplete, or source-spliced.

## Return Calculations

```text
Price Return[t] = Close[t] / Close[t-1] - 1
Total Return[t] = Adj Close[t] / Adj Close[t-1] - 1
```

If `Adj Close` is not a true total-return level or defensible daily proxy, `Total Return` must be blank or explicitly flagged. Do not duplicate price return into total return without documenting that choice.

## Minimum Coverage

Core datasets must cover from 1970-01-01. Because that date was not a U.S. equity trading day, the first observation for trading-day datasets may be the first available trading day at or immediately after that anchor. If a dataset cannot meet this standard, it must remain provisional until the exception is documented in its methodology file and docs/source_registry.md.

Earlier history may be included when the source is documented, the data can be transformed into the canonical contract, validation can be performed against an independent source or methodology, and reconstruction assumptions are explicit.

## Source Boundaries

Long-history datasets may combine sources. Every source boundary must document:

- The last date from the old source and the first date from the new source.
- The reason for the splice.
- Any scaling or rebasing performed at the boundary.
- A validation check across the overlapping period, where overlap exists.

## Incremental Updates

Dataset update scripts must not blindly append rows. They must:

1. Read the existing processed dataset.
2. Refetch a recent overlap window from the live source (Yahoo chart API or equivalent).
3. Replace overlapping dates with the newly fetched values.
4. Sort and de-duplicate by `Date`.
5. Recompute return columns across the stitched dataset.
6. Rewrite CSV and Parquet outputs together.
7. Update build metadata.

## Quality Flags

Each row carries a `Quality Flag` identifying its data provenance. Defined flag values per dataset are documented in the individual methodology files. Common patterns:

- `observed_*`: data comes directly from a market feed or official fixing.
- `model_*`: data is derived from a fitted model (e.g., Federal Reserve yield curve).
- `proxy_*`: data comes from a fund or index that approximates the target exposure but is not the benchmark itself.
