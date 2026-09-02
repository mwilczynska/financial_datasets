# STT — Short-Term U.S. Treasury (SHY-like, 1-3 Year)

Dataset identifier: `short_term_us_treasury`

Backtest alias: `STT`

Status: complete model-derived public-source dataset; CRSP/WRDS constituent-level build is the preferred future upgrade

## Asset Definition

`STT` approximates SHY-like short-duration nominal U.S. Treasury exposure: bonds with roughly 1-3 years remaining maturity, with coupon/distribution reinvestment reflected in `Adj Close` and `Total Return`.

- `Close`: normalized price-return index (no OHLCV; source data is fund/model-level, not tick-level).
- `Adj Close`: normalized total-return index including coupon carry.
- `Price Return` and `Total Return` differ because coupons are included in `Adj Close` but not in `Close`.

## Output Files

| File | Path |
|---|---|
| CSV | `data/processed/short_term_us_treasury.csv` |
| Parquet | `data/processed/short_term_us_treasury.parquet` |
| Manifest | `sources/manifests/short_term_us_treasury.yml` |
| Citation notes | `sources/citations/short_term_us_treasury.md` |
| Build script | `src/build_short_term_us_treasury.py` |
| Update script | `src/update_short_term_us_treasury.py` |
| Test file | `tests/validation/test_short_term_us_treasury_contract.py` |

Coverage starts on `1970-01-02`. The pre-VFISX segment is model-derived, not observed fund or index history.

## Source Chain

| Segment | Dates | Source | Quality flag |
|---|---|---|---|
| Fed model | 1970-01-02 – 1991-10-28 | Federal Reserve nominal yield curve, 2-year synthetic par Treasury | `model_fed_yield_curve_2y_par_treasury_total_return` |
| VFISX proxy | 1991-10-29 – 2002-07-30 | Yahoo Finance chart API, VFISX adjusted close | `observed_yahoo_vfisx_short_treasury_total_return_proxy` |
| SHY observed | 2002-07-31 – present | Yahoo Finance chart API, SHY adjusted close | `observed_yahoo_shy_1_3_treasury_total_return` |

The 2-year synthetic maturity approximates the midpoint of the SHY 1-3 year target maturity band.

## Production Sources

- **Federal Reserve Nominal Yield Curve CSV** (`https://www.federalreserve.gov/data/yield-curve-tables/feds200628.csv`): daily fitted nominal zero-curve parameters from 1961 to present; used to price a synthetic 2-year constant-maturity par Treasury.
- **Yahoo Finance chart API VFISX**: Vanguard Short-Term Treasury Fund Investor Shares adjusted-close returns from approximately 1991-10-29 until SHY history is available.
- **Yahoo Finance chart API SHY**: iShares 1-3 Year Treasury Bond ETF adjusted-close returns from approximately 2002-07-31 onward.

## Validation Sources

- **Raw VFISX Yahoo chart payload**: exact daily return match against the processed VFISX segment.
- **Raw SHY Yahoo chart payload**: exact daily return match against the processed SHY segment.
- **Federal Reserve yield curve raw CSV**: confirms the model-derived pre-VFISX `Adj Close` compounds cumulatively (from 100 to approximately 1142 by late 1991), consistent with the high short-rate environment of the 1970s–80s.

## Rejected or Limited Sources

- **CRSP/WRDS constituent-level data**: preferred future upgrade; requires a licensed subscription.

## Build Method

1. Download the Federal Reserve nominal yield curve CSV; store under `sources/raw/`.
2. For each trading day from `1970-01-02` until VFISX adjusted fund returns begin:
   a. Evaluate the fitted nominal zero curve at 2-year maturity using the Svensson parameterisation.
   b. Price a synthetic constant-maturity par Treasury bond.
   c. `Price Return` = price change only; `Total Return` = price change plus daily coupon carry.
   d. Compound cumulative `Close` and `Adj Close` levels starting at 100.
3. Splice VFISX adjusted-close returns from the first available VFISX return date through the day before SHY daily returns are usable.
4. Splice SHY adjusted-close returns from the first available SHY return date onward.
5. Normalize the full series: `Close` starts at 100 and compounds source price returns; `Adj Close` starts at 100 and compounds source total returns.
6. Mark each row with a source-specific quality flag.

The Fed model segment produces cumulative levels, not one-day relative values, before splicing.

## Update Method

`src/update_short_term_us_treasury.py` triggers a full rebuild from current source data (equivalent to re-running the build script). All three source segments are refetched in the same step.

## Tests

`tests/validation/test_short_term_us_treasury_contract.py` covers:

- Yahoo-compatible schema and required column order.
- First observation date of `1970-01-02`.
- Unique sorted dates.
- Positive `Close` and `Adj Close` levels throughout.
- `Price Return` arithmetic from `Close`.
- `Total Return` arithmetic from `Adj Close`.
- Fed model segment is present, starts on `1970-01-02`, ends before `1991-11-01`, and has cumulative `Adj Close` growth above 150 (confirming coupon carry compounds correctly — actual growth is to ~1142).
- Exact daily `Total Return` match against raw Yahoo VFISX adjusted-close returns for the VFISX segment (>2,000 rows checked).
- Exact daily `Total Return` match against raw Yahoo SHY adjusted-close returns for the SHY segment (>5,000 rows checked).

## Caveats

- The pre-1991 segment is model-derived from Federal Reserve yield curve parameters at a synthetic 2-year maturity. It must not be described as observed fund or constituent-level index history.
- VFISX is only a proxy for SHY-like short Treasury exposure. Its maturity/duration profile and expense ratio differ from SHY's at any given date.
- SHY includes ETF expense, tracking, premium/discount, and trading effects.
- Short-duration bonds have lower price volatility than intermediate or long-duration bonds, so `Price Return` will be small relative to `Total Return` over multi-decade periods — the divergence between `Close` (~100–120 range) and `Adj Close` (~1142 by 1991) reflects the dominance of coupon income in short Treasury total return during the high-rate era.
- A true 1970+ constituent-level dataset requires CRSP/WRDS daily Treasury issue-level data, selecting nominal bonds with 1-3 years remaining maturity and computing coupon-aware daily holding-period returns.
