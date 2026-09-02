# ITT — Intermediate-Term U.S. Treasury (IEF-like, 7-10 Year)

Dataset identifier: `intermediate_term_us_treasury`

Backtest alias: `ITT`

Status: complete model-derived public-source dataset; CRSP/WRDS constituent-level build is the preferred future upgrade

## Asset Definition

`ITT` approximates IEF-like intermediate-duration nominal U.S. Treasury exposure: bonds with roughly 7-10 years remaining maturity, with coupon/distribution reinvestment reflected in `Adj Close` and `Total Return`.

- `Close`: normalized price-return index (no OHLCV; source data is fund/model-level, not tick-level).
- `Adj Close`: normalized total-return index including coupon carry.
- `Price Return` and `Total Return` differ because coupons are included in `Adj Close` but not in `Close`.

## Output Files

| File | Path |
|---|---|
| CSV | `data/processed/intermediate_term_us_treasury.csv` |
| Parquet | `data/processed/intermediate_term_us_treasury.parquet` |
| Manifest | `sources/manifests/intermediate_term_us_treasury.yml` |
| Citation notes | `sources/citations/intermediate_term_us_treasury.md` |
| Build script | `src/build_intermediate_term_us_treasury.py` |
| Update script | `src/update_intermediate_term_us_treasury.py` |
| Test file | `tests/validation/test_intermediate_term_us_treasury_contract.py` |

Coverage starts on `1970-01-02`. The pre-VFITX segment is model-derived, not observed fund or index history.

## Source Chain

| Segment | Dates | Source | Quality flag |
|---|---|---|---|
| Fed model | 1970-01-02 – 1991-10-28 | Federal Reserve nominal yield curve, 8.5-year synthetic par Treasury | `model_fed_yield_curve_8pt5y_par_treasury_total_return` |
| VFITX proxy | 1991-10-29 – 2002-07-30 | Yahoo Finance chart API, VFITX adjusted close | `observed_yahoo_vfitx_intermediate_treasury_total_return_proxy` |
| IEF observed | 2002-07-31 – present | Yahoo Finance chart API, IEF adjusted close | `observed_yahoo_ief_7_10_treasury_total_return` |

The 8.5-year synthetic maturity approximates the midpoint of the IEF 7-10 year target maturity band.

## Production Sources

- **Federal Reserve Nominal Yield Curve CSV** (`https://www.federalreserve.gov/data/yield-curve-tables/feds200628.csv`): daily fitted nominal zero-curve parameters from 1961 to present; used to price a synthetic 8.5-year constant-maturity par Treasury.
- **Yahoo Finance chart API VFITX**: Vanguard Intermediate-Term Treasury Fund Investor Shares adjusted-close returns from approximately 1991-10-29 until IEF history is available.
- **Yahoo Finance chart API IEF**: iShares 7-10 Year Treasury Bond ETF adjusted-close returns from approximately 2002-07-31 onward.

## Validation Sources

- **Raw VFITX Yahoo chart payload**: exact daily return match against the processed VFITX segment.
- **Raw IEF Yahoo chart payload**: exact daily return match against the processed IEF segment.
- **Federal Reserve yield curve raw CSV**: confirms the model-derived pre-VFITX `Adj Close` grows cumulatively rather than remaining flat.

## Rejected or Limited Sources

- **CRSP/WRDS constituent-level data**: preferred future upgrade; requires a licensed subscription.

## Build Method

1. Download the Federal Reserve nominal yield curve CSV; store under `sources/raw/`.
2. For each trading day from `1970-01-02` until VFITX adjusted fund returns begin:
   a. Evaluate the fitted nominal zero curve at 8.5-year maturity using the Svensson parameterisation.
   b. Price a synthetic constant-maturity par Treasury bond.
   c. `Price Return` = price change only; `Total Return` = price change plus daily coupon carry.
   d. Compound cumulative `Close` and `Adj Close` levels starting at 100.
3. Splice VFITX adjusted-close returns from the first available VFITX return date through the day before IEF daily returns are usable.
4. Splice IEF adjusted-close returns from the first available IEF return date onward.
5. Normalize the full series: `Close` starts at 100 and compounds source price returns; `Adj Close` starts at 100 and compounds source total returns.
6. Mark each row with a source-specific quality flag.

The Fed model segment produces cumulative levels, not one-day relative values, before splicing.

## Update Method

`src/update_intermediate_term_us_treasury.py` triggers a full rebuild from current source data (equivalent to re-running the build script). All three source segments are refetched in the same step, so incremental-only appending is not used.

## Tests

`tests/validation/test_intermediate_term_us_treasury_contract.py` covers:

- Yahoo-compatible schema and required column order.
- First observation date of `1970-01-02`.
- Unique sorted dates.
- Positive `Close` and `Adj Close` levels throughout.
- `Price Return` arithmetic from `Close`.
- `Total Return` arithmetic from `Adj Close`.
- Fed model segment is present, starts on `1970-01-02`, ends before `1991-11-01`, and has cumulative `Adj Close` growth above 150 (confirming coupon carry compounds correctly).
- Exact daily `Total Return` match against raw Yahoo VFITX adjusted-close returns for the VFITX segment (>2,000 rows checked).
- Exact daily `Total Return` match against raw Yahoo IEF adjusted-close returns for the IEF segment (>5,000 rows checked).

## Caveats

- The pre-1991 segment is model-derived from Federal Reserve yield curve parameters at a synthetic 8.5-year maturity. It must not be described as observed fund or constituent-level index history.
- VFITX is only a proxy for IEF-like intermediate Treasury exposure. Its maturity/duration profile and expense ratio differ from IEF's at any given date.
- IEF includes ETF expense, tracking, premium/discount, and trading effects.
- A true 1970+ constituent-level dataset requires CRSP/WRDS daily Treasury issue-level data, selecting nominal bonds with 7-10 years remaining maturity and computing coupon-aware daily holding-period returns.
