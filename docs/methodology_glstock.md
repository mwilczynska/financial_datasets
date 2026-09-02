# GLSTOCK - Global All-World Stocks

Dataset identifier: `global_stocks`

Backtest alias: `GLSTOCK`

Status: complete model-derived public-source proxy

## Asset Definition

`GLSTOCK` is a long-horizon global all-world equity total-return proxy. The target exposure is similar to VT, MSCI ACWI, or FTSE All-World: broad global equities in USD with dividends reinvested.

- `Close`: normalized total-return proxy level.
- `Adj Close`: equal to `Close`.
- `Price Return` and `Total Return`: equal daily total-return proxy.

There is no separate observed price index for the full 1970-present chain, so this dataset is a total-return/NAV-style series.

## Output Files

| File | Path |
|---|---|
| CSV | `data/processed/global_stocks.csv` |
| Parquet | `data/processed/global_stocks.parquet` |
| Manifest | `sources/manifests/global_stocks.yml` |
| Citation notes | `sources/citations/global_stocks.md` |
| Build script | `src/build_global_stocks.py` |
| Update script | `src/update_global_stocks.py` |
| Test file | `tests/validation/test_global_stocks_contract.py` |

Coverage starts on `1970-01-02`, the first USLCAP trading date after the 1970 anchor.

## Source Chain

| Segment | Dates | Source | Quality flag |
|---|---|---|---|
| Early annual-anchored model | 1970-01-02 to 1989-12-29 | USLCAP daily path scaled to MSCI World gross annual returns | `model_msci_world_annual_return_scaled_uslcap_daily_proxy` |
| Gap fill | 1990-01-02 to 1990-06-29 | USLCAP daily total-return proxy | `model_uslcap_daily_proxy_gap_until_ff_developed_daily` |
| Developed-market daily | 1990-07-02 to 2008-06-26 | Kenneth French Developed 3 Factors Daily, `Mkt-RF + RF` | `observed_fama_french_developed_market_total_return` |
| Observed all-world ETF | 2008-06-27 onward | Yahoo `VT` adjusted-close returns | `observed_vt_etf_adjusted_total_return` |

## Build Method

1. Load the existing `USLCAP` dataset as the early daily path.
2. For each calendar year 1970-1989, compute USLCAP daily growth and apply a constant daily log-return overlay so the model segment exactly matches published MSCI World gross annual total return for that year.
3. Use unscaled USLCAP total returns for the short 1990 gap before French developed-market daily data begins.
4. Fetch Kenneth French `Developed_3_Factors_Daily_CSV.zip`; compute daily developed-market total return as `(Mkt-RF + RF) / 100`.
5. Fetch Yahoo `VT`; from the first day after VT inception, use VT adjusted-close daily returns.
6. Compound all segments continuously from a normalized level of 100.

## Tests

Validation covers schema, 1970 coverage, unique sorted dates, positive levels, return arithmetic, segment sizing, exact annual matches for the early MSCI-anchored model, exact daily matches to raw French developed-market returns, and exact daily matches to raw VT adjusted-close returns.

## Caveats

- 1970-1989 is not observed daily global equity history. It is a USLCAP daily path model constrained to MSCI World annual returns.
- The first half of 1990 is a U.S. equity proxy because the French developed-market daily file starts on 1990-07-02.
- 1990-2008 is developed markets only; emerging markets enter only in the VT segment.
- The 2008 boundary changes from a gross/factor/index-style return source to a net ETF return source.
- A future upgrade should use licensed daily MSCI ACWI, FTSE All-World, or a constituent-level global equity database.
