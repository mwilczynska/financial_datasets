# USD cash companion validation

Validation performed October 28, 2026. Published companions end October 27,
2026, alongside main's `b900b19` daily refresh. The existing 14 return datasets
and their build manifests have no content changes relative to that main
baseline. Companion models use version `usd_cash_v1:fb732cef312d`, calibrated
through December 31, 2025.

## Reproduction and accounting

- An isolated initial build started with no raw caches and no cash outputs,
  fetched public histories, and published all 13 investable asset companions
  through October 26. The current-source publication gate passed.
- A live incremental refresh of that build passed. Two subsequent incremental
  replays against unchanged cached sources preserved **all output and manifest
  bytes**. This includes CSV, Parquet and model parameters.
- The production companions were subsequently extended to October 27 against
  current main, and refreshed with live sources. They contain 1,678 normalized
  fund cash events and 19,696 asset/constituent cash entitlements. CPI is excluded.
- The complete daily publication gate ran in an isolated copy of current
  outputs with fresh source evidence, including a fresh CPI delivery record.
  All 14 original return histories had **zero inserted or revised observations**
  against current main. The extended cash gate passed source-object hashes,
  cash/share basis, current source identity, calendars, CSV/Parquet equality,
  input hashes, unit arithmetic, daily/event totals and payment/receivable
  accounting. Only the isolated copy's CPI delivery provenance was refreshed;
  committed CPI observations and metadata were preserved.
- Every asset's dates match its existing canonical calendar, beginning
  January 2, 1970. Its original `Total Return` strings are retained exactly.
  No source gaps or original-versus-current-fund total-return differences
  larger than 0.00001 were found in the observed asset periods.
- Tests cover initial builds, repeated increments, issuer precision revisions,
  failed candidate publication, cached issuer-only events, vendor withdrawals,
  source-cache tampering and full-history checks becoming due. The 31-day
  schedule advances after an unchanged full check and does not repeat daily.

The final local full suite passed: **230 passed, 28 skipped** in 74.81 seconds.
All skips were optional raw-source validation checks; no automation check was
skipped. The complete required command is
`python -m pytest -q tests/validation tests/automation`. In this Windows
sandbox the run uses a fresh `--basetemp=data/interim/<run>` because its default
temporary directory is unavailable. Optional raw-source validation tests can
skip on a public checkout; skipped automation tests fail publication. The PR's
Validation and Clean Linux incremental catch-up checks provide the remote
results for its current revision.

The initial full local run exposed three failures in stale, ignored GLD/UGL
legacy validation caches. Replacing those caches with the accepted, hash-checked
current downloads resolved the failures without editing tests or return data.
CSV/Parquet consumer checks agree. As concrete checks, 100 SHY shares entitled
on December 19, 2025 receive USD 25.4847, retaining issuer precision; a USD 10,000
synthetic GLBOND position bought at January 2, 2025 close earns approximately
USD 308.2570 of cash in 2025 under the documented unreinvested unit convention.

## Cash evidence coverage

This table counts the **published full event history**, rather than just the
latest acquisition window. Primary observations can still contain unresolved
disagreements; primary precedence is not a claim of universal source accuracy.
Missing payment dates remain blank in fund events and separately modeled in
the asset ledger.

| Fund | Cash events | Primary amount observations | Missing verified payment dates | Material issuer/vendor amount conflicts |
|---|---:|---:|---:|---:|
| SHY | 291 | 290 | 1 | 1 |
| IEF | 291 | 290 | 1 | 5 |
| TLT | 290 | 290 | 0 | 0 |
| VT | 61 | 40 | 21 | 0 |
| BND | 232 | 120 | 112 | 3 |
| BWX | 172 | 172 | 1 | 4 |
| ISHG | 75 | 75 | 0 | 0 |
| BWZ | 120 | 119 | 1 | 0 |
| UPRO | 47 | 39 | 8 | 0 |
| TYD | 40 | 5 | 35 | 0 |
| TMF | 50 | 4 | 46 | 0 |
| DBC | 9 | 1 | 8 | 0 |
| GLD | 0 | 0 | 0 | 0 |
| UGL | 0 | 0 | 0 | 0 |
| Total | 1,678 | 1,445 | 234 | 13 |

Nine funds have automated issuer histories. Direxion's direct delivery returned
403 for TYD/TMF; Invesco returned 406 or no validated dynamic history for DBC.
Attributed partial primary observations supplement those funds' vendor
histories, without claiming full issuer reconciliation. GLD/UGL routine zero
policies are supported by their prospectus/issuer evidence, with exceptional
payout ingestion retained.

## Return reconciliation limits

Native cash divided by a consistently adjusted preceding price is the cash
contribution. It is not universally equal to adjusted total return minus quoted
price return. Backward dividend adjustments, issuer/vendor conflicts and source
adjustment anomalies create differences. They remain in the published
`Adjustment Residual`, never as extra distributions and never as a reason to
rewrite the canonical return history.

The largest absolute per-fund residuals below are decimal daily return
contributions. Their material size is a data limitation, not a tolerance under
which the amounts were declared equal.

| Fund | Largest absolute residual | Date | Days with absolute residual above 0.0001 |
|---|---:|---|---:|
| SHY | 0.000263187819 | 2012-11-01 | 1 |
| IEF | 0.005826240897 | 2003-09-02 | 6 |
| TLT | 0.002185617989 | 2012-11-01 | 3 |
| VT | 0.000151532079 | 2022-06-21 | 3 |
| BND | 0.002324497523 | 2018-06-01 | 3 |
| BWX | 0.002278831878 | 2012-12-27 | 4 |
| ISHG | 0.000331412341 | 2024-12-18 | 1 |
| BWZ | 0.000040811046 | 2025-08-01 | 0 |
| UPRO | 0.000531472768 | 2018-12-26 | 5 |
| TYD | 0.001361515531 | 2010-12-14 | 7 |
| TMF | 0.001897763073 | 2020-12-10 | 17 |
| DBC | 0.000439285253 | 2008-12-15 | 6 |
| GLD, UGL | 0 | All available observations | 0 |

No unexplained factor jumps without an event remained in this delivered fund
history. That result does not establish complete issuer evidence: vendor-only
events, conflicting amounts and missing payment dates remain separate limits.
The per-event amount/price check uses the exact combined price/rate rounding
bound. A TYD observation that exposed an incorrectly combined bound now has a
regression test that accepts its independent rounding errors and rejects a
materially altered rate.

USLCAP diagnostics identify 42 raw anomalous dates and 34 contaminated months
(including neighboring spike months). Those months use explicitly labeled
models. Earlier S&P/CRSP benchmark-mismatch history is modeled separately.
Small rounding negatives preserve the signed monthly income sum; no material
negative is clipped into an inferred dividend observation.

Historical models remain retrospective and uncertain. Large and special payout
tails are available in `calibration_summary` and the fund event history; the
simple historical backfill does not simulate stochastic future specials.
Source licensing/redistribution constraints remain unresolved as documented
in [the methodology](../methodology_distributions.md) and
[DATA_LICENSE.md](../../DATA_LICENSE.md).
