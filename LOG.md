# Project Log

## 2026-10-24 — CPI outage recovery and current refresh flow

- [PR #6](https://github.com/mwilczynska/financial_datasets/pull/6) added the
  BLS to FRED CPIAUCSL CSV/data-table delivery fallback, source-evidence checks,
  preserved unpublished monthly gaps, and refreshed provenance for repeat CPI
  runs. Both workflows now use checkout/setup-python v7 on Node.js 24 while
  retaining Python 3.11 for the dataset pipeline.
- The [recovery run](https://github.com/mwilczynska/financial_datasets/actions/runs/40121836703)
  used fresh FRED data while BLS still returned HTTP 503. All 14 datasets advanced
  from October 22 to October 23 with one new row each and zero historical revisions.
  Validation passed with 174 tests and 36 expected historical-source skips;
  the gate, README synchronization, and publication passed. Data commit: `8247847`.
- The [operations guide](docs/operations/daily-refresh.md),
  [source policy](docs/update_source_policy.md), and
  [validation guide](docs/validation.md) describe the current flow. Dated entries
  below record their original source choices and are not current source lists.

## 2026-09-26 — Synchronize published README dates

- Added a deterministic README date updater that reads the first and last `Date`
  in each of the 14 processed CSVs and checks every published table row and
  output link. The daily workflow runs it after the publication gate and stages
  `README.md` with validated dataset changes. Hosted validation fails if the
  committed README dates are stale.
- Updated the displayed market-data end dates to 2026-09-25 and the CPI end date
  to 2026-09-26, matching the first hosted incremental publication.

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
