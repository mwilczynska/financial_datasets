# USLCAP — U.S. Large-Cap Equity / S&P 500 Equivalent

Dataset identifier: `us_large_cap_sp500`

Backtest alias: `USLCAP`

Status: complete

## Asset Definition

`USLCAP` is a daily U.S. large-cap equity dataset intended to behave like a Yahoo Finance-compatible S&P 500-style series for backtesting.

- `Close`: S&P 500 price-index level from Yahoo `^GSPC`.
- `Adj Close`: daily total-return-adjusted U.S. large-cap level.

The adjusted history before Yahoo `^SP500TR` availability is a CRSP/French U.S. large-cap/blend proxy, not the official S&P 500 total-return index.

## Output Files

| File | Path |
|---|---|
| CSV | `data/processed/us_large_cap_sp500.csv` |
| Parquet | `data/processed/us_large_cap_sp500.parquet` |
| Manifest | `sources/manifests/us_large_cap_sp500.yml` |
| Citation notes | `sources/citations/us_large_cap_sp500.md` |
| Build script | `src/build_us_large_cap_sp500.py` |
| Update script | `src/update_us_large_cap_sp500.py` |
| Test file | `tests/validation/test_us_large_cap_contract.py` |

Coverage starts on `1970-01-02`, the first trading observation after the `1970-01-01` anchor.

## Production Sources

- **Yahoo `^GSPC`**: daily S&P 500 price-index close, used for `Close` and `Open`/`High`/`Low`/`Volume`.
- **Kenneth French Data Library / CRSP `Portfolios_Formed_on_ME_daily_CSV.zip`**: daily `Hi 30` value-weighted returns, used as the pre-`^SP500TR` large-cap total-return proxy for `Adj Close`.
- **Yahoo `^SP500TR`**: daily S&P 500 total-return index changes, used for `Adj Close` after consecutive daily observations are available.

## Validation Sources

- **FRED `SP500`**: recent independent price-index validation source; compared against `Close` within a 0.01 index-point rounding tolerance.
- **Raw Kenneth French / CRSP file**: exact daily return validation for the pre-`^SP500TR` adjusted period.
- **External annual S&P 500 total-return reference** (Wikipedia): annual sanity check for 1970–1987 adjusted returns; mean absolute difference was 1.57 percentage points, max 4.79 pp in 1975 (expected, because the source is a CRSP proxy not official S&P 500 total return).

## Rejected or Limited Sources

- **Robert Shiller data**: monthly, not acceptable for a daily no-estimate adjusted series.
- **FRED `SP500`**: price-index only and limited to ~10 years of daily history; validation use only.
- **ETF tickers such as `SPY`**: inception dates too recent for the 1970 coverage requirement.

## Build Method

1. Fetch `^GSPC` daily price-index data; use its close level as `Close` and OHLCV fields where available.
2. Fetch Kenneth French / CRSP daily size-portfolio returns (`Portfolios_Formed_on_ME_daily_CSV.zip`).
3. Use the `Hi 30` value-weighted return as the U.S. large-cap total-return proxy before Yahoo `^SP500TR` can provide consecutive daily total-return changes.
4. Fetch Yahoo `^SP500TR` and use its daily return changes after the handoff point.
5. Compound daily adjusted returns into `Adj Close`.
6. Compute `Price Return` from `Close` and `Total Return` from `Adj Close`.
7. Store raw source files under `sources/raw/` and metadata under `sources/manifests/`.

No monthly interpolation, estimated daily dividends, or fund backfills are used.

## Update Method

`src/update_us_large_cap_sp500.py` reads the processed CSV, refetches a configurable overlap window from Yahoo, replaces overlapping rows by `Date`, de-duplicates, recomputes returns, and rewrites CSV and Parquet outputs together. The adjusted series preserves daily total-return coverage from 1970 onward; the update script does not overwrite earlier source-chain logic with ETF-only history.

## Tests

`tests/validation/test_us_large_cap_contract.py` covers:

- Yahoo-compatible schema and column order.
- Date parsing, sorted unique dates, and coverage back to `1970-01-02`.
- Positive `Close` and `Adj Close` levels.
- `Price Return` and `Total Return` arithmetic.
- Recent `Close` comparison against FRED `SP500` within 0.01 rounding tolerance.
- Exact pre-`^SP500TR` daily return match against the raw Kenneth French / CRSP `Hi 30` source.
- Annual 1970–1987 adjusted-return sanity checks against the external total-return reference.

## Caveats

- `Close` is an S&P 500 price-index series; pre-`^SP500TR` `Adj Close` is a CRSP/French large-cap proxy. This is a documented source-chain compromise to satisfy daily coverage back to 1970.
- Pre-`^SP500TR` adjusted returns must not be described as official S&P 500 total return.
- Licensing and redistribution rights for Yahoo-sourced and S&P-derived data must be reviewed before publication outside local research use.
