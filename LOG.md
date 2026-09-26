# Project Log

## 2026-09-26 — Incremental daily publication

- Changed all 14 ordinary `update_*.py` paths to extend the committed processed
  CSV with a bounded recent source overlap. The full `build_*.py` programs remain
  explicit historical rebuilds. This lets a clean GitHub runner update data
  without excluded historical raw files or Yahoo's unavailable `^BCOM` endpoint.
- Current observations come from Yahoo's chart API
  (`https://query1.finance.yahoo.com/v8/finance/chart/`), LBMA Gold PM
  (`https://prices.lbma.org.uk/json/gold_pm.json`), and BLS CPI-U
  (`https://api.bls.gov/publicAPI/v2/timeseries/data/`), retrieved on
  2026-09-26 for the local catch-up check. The approved source definitions,
  redistribution caveats, and transformations remain in `docs/source_registry.md`,
  `docs/update_source_policy.md`, and the per-dataset methodology files.
- The recent Yahoo adjusted-close returns continue each observed ETF segment;
  GLBOND and GLSTBOND retain their documented blends and fee treatment. GOLDPM
  uses LBMA spot `Close` and GLD adjusted returns. CPI interpolates newly
  bracketed monthly observations and carries forward the latest release.
- A clean processed baseline ending around 2026-07-22 was extended through
  2026-09-25 for market datasets and 2026-09-26 for CPI. The resulting recent
  dates, quality flags, and returns were compared with the independently run
  local historical builders; all dates and flags matched. Most recent return
  differences were zero at stored precision; the two global bond blends differed
  by at most about 1e-7 in daily return after separate Yahoo retrievals. The local
  validation suite had 116 passes and 36 historical-raw skips; the new diff
  gate checks the unchanged history and mandatory recent source responses.
- Added a 09:17 America/New_York GitHub Actions refresh with pinned direct
  dependencies. It commits only validated processed outputs and build metadata.
  Failures create or update an issue assigned to the repository owner; no
  automated source or methodology repair is attempted.
