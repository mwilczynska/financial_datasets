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
