# Validation Tests

Validation tests check generated datasets before they are used for backtests.

Initial focus:

- Yahoo-compatible schema.
- Minimum `1970-01-01` coverage.
- Duplicate dates.
- Non-positive levels.
- Return arithmetic.
- Independent-source overlap checks.

## Public checkout

The public release includes generated datasets but not downloaded source caches by default. Historical source-backed tests may skip when their required raw input is absent, with an explicit reason. Running the same suite after retrieving the raw inputs executes those checks. The daily publisher also runs `tests/automation`, where any skipped check blocks publication, and the mandatory current-source gate across all 20 datasets.

Daily updates do not refresh historical raw caches. A local cache can therefore
lag newly published processed rows, particularly for full-history GLD/UGL
comparisons. Keep source-backed caches current for those tests or use a clean
checkout matching the hosted environment; do not weaken the assertions to fit
an old cache.

## CPI delivery and publication

The historical CPI contract compares observed monthly levels with raw BLS data
when that cache is present. The current publication gate accepts the recorded
BLS JSON, FRED CPIAUCSL CSV, or verified FRED CPIAUCSL data table and independently
checks its provider, hash, retrieval time, target, coverage, committed overlap,
and derived daily levels. It does not require a BLS response file when the
accepted delivery came from FRED.

`tests/automation/test_cpi_source_fallback.py` uses fixtures for both FRED
formats and real publication-check code. It covers transient failures,
unchanged repeat updates, unpublished monthly gaps, invalid or mismatched
observations, stale responses, and tampered provenance. These fixtures require
no live provider or historical source download. See the
[validation guide](../../docs/validation.md) and
[operations guide](../../docs/operations/daily-refresh.md).

## CMDTY daily GSCI replacement

The CMDTY contract tests check its preserved calendar, daily ER/TR source
transformation, segment labels and counts, separate splices, CSV/Parquet
agreement, metadata hashes, and later return preservation. Source-backed checks
also validate the pinned workbook and all 44 published reference gates when its
ignored raw cache is present. The automation suite covers migration idempotence,
invalid inputs, concurrent updates, output rollback, and ordinary DBC updates.
See [the CMDTY methodology](../../docs/methodology_cmdty.md) and
[implementation review](../../docs/research/cmdty_daily_implementation_astra_review.md).

Run the required suites and README coverage check from the repository root:

```text
python -m pytest -q tests/validation tests/automation
python scripts/update_readme_dates.py --check
```
