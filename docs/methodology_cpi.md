# CPI - U.S. CPI-U Inflation Index

Dataset identifier: `cpi_inflation`

Backtest/utility alias: `CPI`

Status: complete model-derived daily deflator from monthly CPI

## Asset Definition

`CPI` represents U.S. CPI-U, all urban consumers, U.S. city average, all items, seasonally adjusted (`CUSR0000SA0`).

- `Close`: CPI-U index level, 1982-84=100.
- `Adj Close`: equal to `Close`.
- `Price Return` and `Total Return`: daily inflation rate implied by the CPI level.

This is not observed daily inflation data. BLS publishes this CPI series monthly; daily rows are a derived deflator for daily backtesting analysis.

## Output Files

| File | Path |
|---|---|
| CSV | `data/processed/cpi_inflation.csv` |
| Parquet | `data/processed/cpi_inflation.parquet` |
| Manifest | `sources/manifests/cpi_inflation.yml` |
| Citation notes | `sources/citations/cpi_inflation.md` |
| Build script | `src/build_cpi_inflation.py` |
| Update script | `src/update_cpi_inflation.py` |
| Test file | `tests/validation/test_cpi_inflation_contract.py` |

Coverage starts on `1970-01-01`. The current build runs through `2026-06-19`; the latest BLS monthly CPI observation in the raw source is `2026-05-01`.

## Production Source

- BLS public API, series `CUSR0000SA0`: monthly seasonally adjusted CPI-U, index 1982-84=100.

## Validation Source

- FRED `CPIAUCSL` is the same CPI-U concept and remains the external validation reference. Direct FRED CSV retrieval timed out in this environment during implementation.

## Build Method

1. Fetch BLS `CUSR0000SA0` in 10-year chunks and store the raw JSON under `sources/raw/`.
2. Parse monthly observations on the first day of each month.
3. Emit exact month-start CPI rows with `observed_bls_monthly_cpi_u_level`.
4. Fill days between adjacent monthly observations by constant log interpolation and flag them `model_daily_log_interpolated_monthly_cpi_u`.
5. Carry the latest published CPI level forward after the most recent observation and flag those rows `carried_forward_latest_monthly_cpi_u_level`.
6. Set `Close == Adj Close`; compute daily return columns from the level.

## Update Method

`src/update_cpi_inflation.py` calls the full build. Rerun after each monthly CPI release to replace carried-forward rows with newly bracketed/interpolated values.

## Tests

Validation checks schema, calendar-daily coverage, unique sorted dates, positive levels, `Close == Adj Close`, return arithmetic, exact month-start matches to raw BLS values, and presence of interpolation/carry-forward quality flags.

## Caveats

- Daily CPI rows are a model-derived plotting deflator, not observed daily CPI.
- Constant log interpolation uses both monthly endpoints, so it is appropriate for historical real-return display, not for real-time point-in-time inflation nowcasting.
- After the latest monthly release, the level is carried forward until the next build.
