# LTT — Long-Term U.S. Treasury (TLT-like, 20+ Year)

Dataset identifier: `long_term_us_treasury`

Backtest alias: `LTT`

Status: complete model-derived public-source dataset; CRSP/WRDS constituent-level build is the preferred future upgrade

## Asset Definition

`LTT` approximates TLT-like long-duration nominal U.S. Treasury exposure: bonds with roughly 20+ years remaining maturity, with coupon/distribution reinvestment reflected in `Adj Close` and `Total Return`.

- `Close`: normalized price-return index (no OHLCV; source data is fund/model-level, not tick-level).
- `Adj Close`: normalized total-return index including coupon carry.
- `Price Return` and `Total Return` differ because coupons are included in `Adj Close` but not in `Close`.

## Output Files

| File | Path |
|---|---|
| CSV | `data/processed/long_term_us_treasury.csv` |
| Parquet | `data/processed/long_term_us_treasury.parquet` |
| Manifest | `sources/manifests/long_term_us_treasury.yml` |
| Citation notes | `sources/citations/long_term_us_treasury.md` |
| Build script | `src/build_long_term_us_treasury.py` |
| Update script | `src/update_long_term_us_treasury.py` |
| Test file | `tests/validation/test_long_term_us_treasury_contract.py` |

Coverage starts on `1970-01-02`. The pre-VUSTX segment is model-derived, not observed fund or index history.

## Source Chain

| Segment | Dates | Source | Quality flag |
|---|---|---|---|
| Fed model | 1970-01-02 – 1986-05-19 | Federal Reserve nominal yield curve, 25-year synthetic par Treasury | `model_fed_yield_curve_25y_par_treasury_total_return` |
| VUSTX proxy | 1986-05-20 – 2002-07-30 | Yahoo Finance chart API, VUSTX adjusted close | `observed_yahoo_vustx_long_treasury_total_return_proxy` |
| TLT observed | 2002-07-31 – present | Yahoo Finance chart API, TLT adjusted close | `observed_yahoo_tlt_20_plus_treasury_total_return` |

Within the Fed model segment, the **yield input** follows a stability hierarchy across sub-periods (see Build Method below).

## Production Sources

- **Federal Reserve Nominal Yield Curve CSV** (`https://www.federalreserve.gov/data/yield-curve-tables/feds200628.csv`): daily fitted nominal zero-curve parameters from 1961 to present; `SVENY25`/`SVENY30` pre-computed smoothed zero rates used where available (from Nov 1985 to VUSTX start).
- **Yahoo Finance chart API ^TYX**: CBOE 30-year Treasury yield index; available from 1977-02-15; used as the primary observed long-rate input for the 1977–1985 sub-period.
- **Fed curve `SVENY10`** (available from Aug 1971): used as a proxy for the 25-year yield in 1971–1977. The yield curve was flat to inverted in this period, so 10-year and 25-year yields were within ~50 bps of each other.
- **Svensson BETA-fitted 10-year rate**: used as a last resort for 1970–Aug 1971 when no pre-computed SVENY columns are available. The Svensson fit is stable at 10-year maturity; the raw BETA parameters are numerically ill-conditioned when extrapolated to 25 years in this period, which is why the pre-computed SVENY25 is NaN before Nov 1985.
- **Yahoo Finance chart API VUSTX**: Vanguard Long-Term Treasury Fund Investor Shares adjusted-close returns from approximately 1986-05-19 until TLT history is available.
- **Yahoo Finance chart API TLT**: iShares 20+ Year Treasury Bond ETF adjusted-close returns from approximately 2002-07-31 onward.

## Validation Sources

- **Raw VUSTX Yahoo chart payload**: exact daily return match against the processed VUSTX segment.
- **Raw TLT Yahoo chart payload**: exact daily return match against the processed TLT segment.
- **Federal Reserve yield curve raw CSV**: confirms the model-derived pre-VUSTX `Adj Close` compounds from 100 to approximately 194 between 1970 and 1986, consistent with high nominal coupon carry during that period.

## Rejected or Limited Sources

- **Svensson BETA extrapolation at 25 years**: rejected as the primary long-rate input for the pre-1985 period. The BETA0 parameter (the long-run asymptote of the yield curve) is numerically ill-conditioned in the early 1970s, causing the fitted 25-year yield to oscillate by hundreds of basis points on consecutive days. The Federal Reserve's own pre-computed `SVENY25` column is `NaN` before November 1985, which is the Fed's signal that these extrapolated values are unreliable. Using these raw parameters produced a spurious ~38% intra-year drawdown in 1970.
- **FRED DGS30**: daily 30-year constant-maturity yield; a good candidate model input. FRED CSV retrieval timed out in this environment, so Yahoo `^TYX` is used instead for the 1977–1985 sub-period. The DGS30 was also discontinued from 2002-02-18 to 2006-02-09.
- **CRSP/WRDS constituent-level data**: preferred future upgrade; requires a licensed subscription.

## Build Method

1. Download the Federal Reserve nominal yield curve CSV and Yahoo `^TYX` (30-year yield); store under `sources/raw/`.
2. For each trading day from `1970-01-02` until VUSTX adjusted fund returns begin:
   a. Determine the best available stable long-rate proxy using the hierarchy:
      - `SVENY25` or `SVENY30` from the Fed curve (available Nov 1985 to VUSTX start).
      - Yahoo `^TYX` 30-year observed yield (available 1977-02-15 to Nov 1985).
      - `SVENY10` from the Fed curve as a proxy (available Aug 1971 to Feb 1977; curve was flat/inverted so 10y ≈ 25y within ~50 bps).
      - Svensson-fitted 10-year yield from BETA parameters (1970 to Aug 1971; stable at 10-year maturity).
   b. Price a synthetic 25-year constant-maturity par Treasury at a flat yield (all cashflows discounted at the selected rate). The previous-day price is computed explicitly (not assumed to be 100, since continuous compounding yields ≠ par at 100 exactly).
   c. `Price Return` = price change only; `Total Return` = price change plus daily coupon carry.
   d. Compound cumulative `Close` and `Adj Close` levels starting at 100.
3. Splice VUSTX adjusted-close returns from the first available VUSTX return date through the day before TLT daily returns are usable.
4. Splice TLT adjusted-close returns from the first available TLT return date onward.
5. Normalize the full series: `Close` starts at 100 and compounds source price returns; `Adj Close` starts at 100 and compounds source total returns.
6. Mark each row with a source-specific quality flag.

The Fed model segment produces cumulative levels, not one-day relative values, before splicing. A regression test prevents regression to the earlier bug where the synthetic segment remained flat around 100.

## Required Future Upgrade

A true 1970+ constituent-level dataset should be built from CRSP/WRDS daily Treasury issue-level data:

1. Pull daily nominal U.S. Treasury issue records from 1970 onward (date, identifier, clean price, accrued interest, coupon, maturity, market value, issue type).
2. Exclude TIPS, Treasury bills, STRIPS, and non-standard issues.
3. Select bonds with at least 20 years remaining maturity on each date.
4. Compute each bond's daily holding-period total return from dirty-price change plus coupon cash flows on coupon dates.
5. Market-value weight eligible bonds to produce a daily 20+ year Treasury total-return index.
6. Validate post-2002 daily and cumulative behavior against TLT adjusted returns.

## Update Method

`src/update_long_term_us_treasury.py` triggers a full rebuild from current source data (equivalent to re-running the build script). All three source segments are refetched in the same step.

## Tests

`tests/validation/test_long_term_us_treasury_contract.py` covers:

- Yahoo-compatible schema and required column order.
- First observation date of `1970-01-02`.
- Unique sorted dates.
- Positive `Close` and `Adj Close` levels throughout.
- `Price Return` arithmetic from `Close`.
- `Total Return` arithmetic from `Adj Close`.
- Fed model segment is present, starts on `1970-01-02`, ends before `1986-05-20`, and has cumulative `Adj Close` growth above 150 (confirming coupon carry compounds correctly).
- Exact daily `Total Return` match against raw Yahoo VUSTX adjusted-close returns for the VUSTX segment (>3,000 rows checked).
- Exact daily `Total Return` match against raw Yahoo TLT adjusted-close returns for the TLT segment (>5,000 rows checked).

## Caveats

- The pre-1986 segment is model-derived, not observed fund or constituent-level index history.
- For 1970–1977, the 10-year rate (SVENY10 or Svensson-fitted) is used as a proxy for the 25-year yield. In the flat/inverted yield curve environment of this period the two were within ~50 bps, but this overstates slightly the long-rate level when the curve was inverted (short rates > long rates). This produces a mild positive bias in total returns vs a true 25-year yield during periods of falling rates.
- For 1977–1985, `^TYX` (30-year yield index from CBOE) is used. This is observed market data, not a model extrapolation.
- VUSTX is only a proxy for TLT-like long Treasury exposure. Its benchmark and duration profile differ from TLT's.
- TLT includes ETF expense, tracking, premium/discount, and trading effects.
- A true 1970+ constituent-level dataset requires CRSP/WRDS daily Treasury issue-level data selecting bonds with 20+ years remaining maturity.
