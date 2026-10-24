# Daily dataset refresh operations

The [daily workflow](../../.github/workflows/daily-refresh.yml) extends all 14
datasets from their committed processed CSVs. Ordinary refreshes do not need
historical raw caches; full rebuilds and source-backed historical tests use
those inputs. Source definitions and acceptance rules are
in the [source policy](../update_source_policy.md),
[registry](../source_registry.md), and [validation guide](../validation.md).

## Scheduled publication

The workflow is scheduled for 09:17 `America/New_York`, targeting the previous
calendar day. It can also be dispatched manually on `main`. Runs share the
`daily-dataset-refresh` concurrency group with cancellation disabled, and the
refresh job has a 45-minute timeout.

Both daily and validation workflows use `actions/checkout@v7` and
`actions/setup-python@v7`, whose action runtime is Node.js 24. The dataset code
runs on Python 3.11 with the dependencies in `requirements.txt`. Updater output
is unbuffered so source transitions appear when they occur.

The publisher performs these steps in order:

1. Check out `main`, install pinned dependencies, and select the inclusive target date.
2. Run `python src/update_all_datasets.py --end-date YYYY-MM-DD` in dependency order.
   All updates must succeed before `tests/validation` and `tests/automation` run.
3. Run `python scripts/check_daily_diff.py --end-date YYYY-MM-DD` across all 14
   datasets, including unchanged files. It checks preserved history, CSV/Parquet
   agreement, metadata, source values, freshness, and return arithmetic.
4. Synchronize and check the README dataset dates.
5. Reject unexpected tracked changes, stage only the explicit
   [publication allowlist](../../scripts/stage_daily_outputs.py), and commit/push
   validated outputs. The allowlist covers CSV/Parquet pairs, 14 build manifests,
   and `README.md`; downloaded raw sources remain excluded.

An update or validation failure skips publication. Any temporary updates from
earlier datasets remain in the runner checkout. A failed refresh creates or
comments on an open failure issue; the workflow does not automatically close
that issue after recovery. It cannot alert on a scheduled run that never starts.

## CPI source order

The incremental updater uses [cpi_sources.py](../../src/cpi_sources.py):

1. Request BLS `CUSR0000SA0` through the public API. Its six-retry policy can
   spend about 4.5 minutes in backoff on repeated HTTP 503 responses; request
   timeouts and honored `Retry-After` headers can extend that wait.
2. After a transient BLS connection/time-out error, exhausted retries, or HTTP
   429/500/502/503/504, fetch FRED `CPIAUCSL` through its standard complete-series
   CSV export. Requests identify this application and filter dates locally.
3. After a transient CSV failure, fetch FRED's public CPIAUCSL data table and
   verify its BLS attribution, series, units, frequency, and seasonal adjustment.

Each FRED route has one retry. CSV connection/read timeouts are 10/20 seconds;
the table uses 10/30 seconds. `Retry-After` headers are honored. A malformed
payload, incorrect series, non-transient HTTP error, or conflicting monthly
observations blocks the update; these are not reasons to bypass validation.

FRED delivers the same upstream BLS series. Its overlap must include the latest
committed monthly anchor and at least three matching monthly observations, with
exactly the same observed-month coverage and agreement within `1e-9`. Existing
unpublished months remain interpolated; new monthly observations must be
consecutive. The latest monthly observation must be within 90 days of the
target, and the calendar-daily output must reach that target.

The fallback applies to ordinary incremental updates. The full CPI builder
still retrieves BLS history directly. Neither a stale local response nor
carrying an unverified cache through an outage is an accepted delivery route.

## Reading provenance and logs

`sources/manifests/cpi_inflation_build.json` retains BLS as the data origin.
The actual delivery for an incremental run is the single record under
`incremental_update.recent_sources`:

| Record key | Raw evidence under `sources/raw/incremental/` |
|---|---|
| `BLS_CUSR0000SA0` | `cpi_bls_recent.json` |
| `FRED_CPIAUCSL` | `cpi_fred_recent.csv` |
| `FRED_CPIAUCSL_TABLE` | `cpi_fred_recent.html` |

The record includes the URL, series ID, SHA-256, retrieval timestamp, requested
end date, first/last monthly dates, and fallback reason where relevant. The gate
independently checks this evidence, including a retrieval age of at most one day.
A repeat CPI update can refresh metadata without changing daily rows, so an
unchanged CSV does not guarantee there will be no metadata commit.

`BLS CPI temporarily unavailable; checking FRED ...` is a recovery transition,
not the final job result. A following `FRED CPI verified against committed BLS
overlap` message indicates that the downloaded monthly data passed the overlap
checks. Confirm the test, gate, and commit/push steps also finish successfully.

A Node.js deprecation annotation refers to the referenced action versions.
Inspect checkout/setup results and the failed step's traceback separately.
The current v7 actions declare Node.js 24; the dataset updater remains Python.

## Recovering a failed run

1. Inspect the failed step and final exception. Distinguish a recovered primary
   source error from an overall update failure, and inspect the diff-gate summary
   if data updated but publication was blocked.
2. Check the recorded source route and its evidence. An overlap disagreement,
   wrong series, stale observation, or hash mismatch needs investigation. Do not
   skip the gate or enable a historical rebuild to get past a daily failure.
3. After fixing a workflow/updater or restoring accepted source access, start a
   new **Run workflow** on `main`. Supply an optional inclusive `end_date`; a
   blank value means yesterday in New York. Do not request a date before any
   dataset's committed last date. The updater catches up from the committed baseline.

```text
gh workflow run daily-refresh.yml --repo mwilczynska/financial_datasets --ref main -f end_date=YYYY-MM-DD
gh run list --repo mwilczynska/financial_datasets --workflow daily-refresh.yml --limit 5
gh run view RUN_ID --repo mwilczynska/financial_datasets
```

GitHub [re-runs retain the original event's commit and ref](https://docs.github.com/en/actions/how-tos/manage-workflow-runs/re-run-workflows-and-jobs).
A new dispatch on `main` selects the current workflow definition after a repair.

4. Verify success of the update/tests, publication gate, README check, and
   commit/push. Confirm the published commit and generated coverage dates on
   `main`; a green standalone validation job alone does not publish data.
5. Close the resolved failure issue after publication is confirmed, then sync
   any clean local checkout. Preserve unrelated local changes.

## Verified recovery on 2026-10-24

The [original run](https://github.com/mwilczynska/financial_datasets/actions/runs/40112342165)
failed on CPI with exhausted BLS HTTP 503 retries during the
[announced BLS maintenance window](https://www.bls.gov/bls/maintenance10212026.htm).
No partial dataset outputs were pushed.

[PR #6](https://github.com/mwilczynska/financial_datasets/pull/6) restored the
flow. Its [clean Linux catch-up](https://github.com/mwilczynska/financial_datasets/actions/runs/40121308985)
and the [production recovery run](https://github.com/mwilczynska/financial_datasets/actions/runs/40121836703)
both passed while BLS still returned 503. The publisher fetched fresh FRED data,
passed 174 tests with 36 expected historical-source skips, and published
[`8247847`](https://github.com/mwilczynska/financial_datasets/commit/82478475b82ca9877677f28ef4683048ff3d3930).
All 14 datasets added October 23 with one new row each and zero historical
revisions; README dates and build metadata were synchronized. Failure issue
[#5](https://github.com/mwilczynska/financial_datasets/issues/5) was then closed.

The [published CPI metadata](https://github.com/mwilczynska/financial_datasets/blob/82478475b82ca9877677f28ef4683048ff3d3930/sources/manifests/cpi_inflation_build.json)
records `FRED_CPIAUCSL`, its retrieval time and raw-response hash, and the latest
monthly observation of September 2026. These are dated recovery observations;
use current generated metadata for later runs.
