# Daily refresh failure: 2026-09-30

The scheduled refresh failed because the LBMA Gold PM JSON endpoint denied the
GOLDPM request with HTTP 403. The failure occurred before validation and
publication. No dataset outputs were pushed by the failed run.

## Verified observations

- [Failed run 36758700168](https://github.com/mwilczynska/financial_datasets/actions/runs/36758700168)
  started at 2026-09-30 18:27:25 UTC and requested data through 2026-09-29.
- Failed job/step: `refresh` / `Incremental update and validation suite`.
- Failed dataset: GOLDPM (`gold`), task 5 of 14.
- Exact exception:
  `requests.exceptions.HTTPError: 403 Client Error: Forbidden for url: https://prices.lbma.org.uk/json/gold_pm.json`.
- `src/update_gold.py` called `update_asset`, which called `build_recent_rows`.
  The exception was raised at `response.raise_for_status()` for the LBMA request
  in `src/incremental_update.py` (line 250 in the failed revision).
- USLCAP, STT, ITT, and LTT successfully appended September 29 observations in
  the temporary runner checkout. GOLDPM then failed. The remaining nine tasks,
  including CMDTY and GOLD2X, were not reached.
- The validation suite, publication gate, README synchronization, and
  commit/push steps were skipped. The first four temporary updates therefore
  were not published either.
- [Run 36613600476](https://github.com/mwilczynska/financial_datasets/actions/runs/36613600476)
  succeeded on September 29 and published market observations through
  September 28; CPI follows its separate daily calendar.
- Comparing that successful run's input commit `57a44356c79cdbeb0cc76ee2fa74be88c55f82fb`
  with the failed run's input commit `20396a64b4203cb9d06b4d096e473f268a57684b`
  showed only processed outputs, build metadata, and README changes. No updater,
  dependency, or workflow code changed between the runs.
- One standard local request using the updater's existing requests session on
  2026-09-30 at 18:56:16 UTC also received HTTP 403. The server identified itself
  as Cloudflare, and the returned HTML was a block page rather than gold data.

The evidence establishes a current failure in access to the LBMA endpoint.
It does not establish which Cloudflare rule denied the request or whether the
restriction is temporary.

## Why two emails arrived

The workflow's `notify_failure` job created
[issue #3](https://github.com/mwilczynska/financial_datasets/issues/3) after the
refresh failed. Its `gh issue create` command includes
`--assignee "$GITHUB_REPOSITORY_OWNER"`, which assigned the same issue to
`mwilczynska`. The creation email and assignment email describe one incident.

## Source access and recovery

The current [LBMA precious-metal prices page](https://www.lbma.org.uk/prices-and-data/lbma-precious-metal-prices)
states that historical price tables have moved to MyLBMA and that viewing them
requires the relevant IBA licence. The
[portal access form](https://portal.lbma.org.uk/contact-us/) describes access
requests and licence eligibility checks. These statements are relevant to
selecting a supported data route; they do not prove that licensing caused this
specific Cloudflare block.

GOLDPM's contract requires LBMA PM USD/oz for `Close` and `Price Return`, with
GLD adjusted-close returns driving `Adj Close` and `Total Return`. The existing
GLD-step flag covers dates without an LBMA fixing; it does not establish that a
failed download means no fixing exists. Using GLD as a replacement price source
would change the dataset's methodology. Reusing a cached response cannot supply
the missing current observations.

Recovery options:

1. Restore supported access to the same LBMA PM fixing, through LBMA/IBA or an
   authorized data provider. Confirm available automated delivery and applicable
   usage/redistribution terms, then validate the new delivery route against the
   committed overlap.
2. If that route is unavailable, separately evaluate a replacement daily spot
   price source and explicitly approve the resulting methodology and provenance
   changes before publication.

Once current gold prices are available, perform a catch-up from the current
`main` baseline, run the dataset validation suite and `check_daily_diff.py`, and
then publish through the daily workflow. A later retry may succeed if the access
restriction clears; the local probe did not demonstrate recovery.

## Verification and local evidence

Replayed the actual recorded LBMA HTTP 403 against isolated copies of the local
gold baseline, supplying a synthetic GLD window solely to reach the LBMA
request. The update raised the expected HTTP error. The isolated gold CSV,
Parquet, and build metadata had identical SHA-256 hashes before and after the
failure. This verifies failure handling; it does not validate a successful live
catch-up. The existing automation suite also passed: `3 passed`.

Production datasets, updater code, workflows, and commodities research were
unchanged during this investigation. This note is the sole tracked addition.

Evidence is kept under the ignored
`sources/raw/automation_incident_2026_09_30/` directory:

| Artifact | Coverage / purpose |
|---|---|
| `failed_run.json` | Run metadata and step outcomes for the September 30 failure |
| `failed_step.log` | Failed updater step, including the traceback |
| `github_evidence_manifest.json` | Run URL, access timestamps, SHA-256 hashes, and coverage |
| `lbma_gold_pm_response.body` | HTTP 403 HTML response; no gold observations returned |
| `lbma_gold_pm_probe.json` | Source URL, access timestamp, response status, hash, and unresolved access/redistribution constraints |

LBMA response SHA-256:
`c1b144fe1ac6b2da7d9b6a9fddb8ba9231b7f18b15cc8fb6316df342822db887`.

Disposable investigation scripts and the isolated verification result are in
the ignored `data/interim/` directory. No issue comment, issue closure, rerun,
commit, or push was performed.
