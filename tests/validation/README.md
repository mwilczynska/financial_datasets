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

The public release includes generated datasets but not downloaded source caches by default. The validation hook skips only tests that require one of those absent raw files, with an explicit reason. Running the same suite after retrieving the raw inputs executes those checks.

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
