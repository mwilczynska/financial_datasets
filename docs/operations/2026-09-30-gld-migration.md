# GLD migration following the daily-refresh failure

The source switch begins at Yahoo GLD's first available daily quote,
**2004-11-18**, rather than at the outage date. Both observed indices now follow
GLD: Close follows market close and Adj Close follows adjusted close. Their
separate constant scales anchor to the preceding modeled levels on 2004-11-17.
The initial ETF quote has zero splice return; subsequent returns follow GLD.
Modern Close is an index rather than a USD-per-ounce fixing.

The published pre-GLD model remains unchanged. LBMA is no longer requested by
ordinary rebuilding, daily updating, or current-source publication validation.
An explicit optional historical-source refresh still needs LBMA access.

GOLD2X retains its original synthetic inputs: pre-GLD spot returns and the frozen
previously published spot returns through UGL inception in
`sources/derived/gold_2x_historical_spot_returns.csv`. Provenance and checksums
are recorded beside that file. A scoped Git attribute preserves the archive's
exact bytes on Windows and Linux. Observed leveraged returns still use UGL.

## Verified results

- Gold coverage: 14,270 rows, 1970-01-02–2026-09-29; 5,499 observed GLD rows.
- All 8,771 pre-GLD rows are unchanged.
- Existing GLD total returns changed by at most 1e-10, from decimal rounding.
- All 14,268 previously published GOLD2X rows are unchanged; two UGL rows were
  appended through 2026-09-29.
- CSV/Parquet values, return arithmetic, source proportionality, earliest quote,
  and metadata hashes were verified.
- The actual GLD updater completed without changes on a repeat run, making no
  LBMA request. Failure fixtures preserve CSV, Parquet, and metadata.
- Full suite: 128 passed, 32 historical-cache checks skipped. After final archive
  integrity and builder changes, focused gold/automation checks: 32 passed,
  two skipped because the raw historical LBMA cache is absent. No automation
  check skipped.
- The real daily gate passed for both gold and GOLD2X against an isolated local
  migrated baseline: two new rows each and zero historical revisions. No LBMA
  response file was present. The production historical revision guard remains
  unchanged.

Source retrieval and preservation evidence is retained locally under ignored
`sources/raw/gld_switch_2026_09_30/`. Scripts are in ignored `data/interim/`.

## Publication

This is an intentional historical methodology change, so the migration code,
definitions, preserved input, and rebuilt outputs must be committed together
before the unattended workflow resumes from that baseline. The daily job must
not be allowed to rewrite decades of history as a routine refresh. Its existing
publication guard correctly rejects such a change against the old baseline.

Migration commit `cf22cae` was pushed to GitHub main in merge commit `ac31498`,
which also retained the September 27–28 automated refreshes. Post-merge
validation passed: 129 tests passed and 32 historical-cache checks skipped.
Both gold publication checks also passed against the committed GLD baseline.

The scheduled job now uses the GLD fix. It removes the specific LBMA HTTP 403
failure; other required sources can still fail independently. No manual daily
workflow rerun, issue message, or closure was performed. Commodities research
is separate.
