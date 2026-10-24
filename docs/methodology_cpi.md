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

Coverage starts on `1970-01-01`. The README dataset table and build metadata record the current coverage and latest monthly observation.

## Production Source

- BLS public API, series `CUSR0000SA0`: monthly seasonally adjusted CPI-U, index 1982-84=100.
- During a transient BLS API outage, FRED `CPIAUCSL` may deliver the same BLS monthly observations. Build metadata records the actual delivery route and response hash.

## Validation Source

- FRED `CPIAUCSL` republishes the same seasonally adjusted BLS CPI-U series and serves as the external validation reference and outage fallback.

## Build Method

1. Fetch BLS `CUSR0000SA0` in 10-year chunks and store the raw JSON under `sources/raw/`.
2. Parse monthly observations on the first day of each month.
3. Emit exact month-start CPI rows with `observed_bls_monthly_cpi_u_level`.
4. Fill days between adjacent monthly observations by constant log interpolation and flag them `model_daily_log_interpolated_monthly_cpi_u`.
5. Carry the latest published CPI level forward after the most recent observation and flag those rows `carried_forward_latest_monthly_cpi_u_level`.
6. Set `Close == Adj Close`; compute daily return columns from the level.

## Update Method

The ordinary update starts from the committed processed CSV and fetches only recent BLS `CUSR0000SA0` monthly observations. A new release replaces the previously carried-forward days with documented log-interpolated levels from the preceding monthly anchor, then appends through the requested calendar day. Earlier history is preserved. The full historical builder remains available with `--full-rebuild`.

After BLS connection/time-out errors, exhausted retries, or transient HTTP errors, the updater can fetch FRED `CPIAUCSL`. It requires the latest committed monthly anchor, at least three matching committed monthly observations, identical observed-month coverage in the overlap, consecutive new monthly observations, and a latest observation no more than 90 days before the target. Every overlapping monthly observation must agree with the committed BLS data within 1e-9. Existing unpublished months, such as October 2025, retain the established daily interpolation. Any overlap disagreement blocks the fallback instead of revising history through a secondary delivery route. A BLS data-contract error also blocks publication.

The publication gate independently checks the saved response against its recorded SHA-256, provider, series ID, requested date, coverage, retrieval time, and committed overlap, then recomputes daily tail levels and flags. A repeat update that changes no daily rows still refreshes this delivery evidence. If neither live delivery route validates, CSV, Parquet, and build metadata remain unchanged and the workflow does not publish.

## Tests

Validation checks schema, calendar-daily coverage, unique sorted dates, positive levels, `Close == Adj Close`, return arithmetic, exact month-start matches to raw BLS values, and presence of interpolation/carry-forward quality flags.

## Caveats

- Daily CPI rows are a model-derived plotting deflator, not observed daily CPI.
- Constant log interpolation uses both monthly endpoints, so it is appropriate for historical real-return display, not for real-time point-in-time inflation nowcasting.
- After the latest monthly release, the level is carried forward until the next build.
