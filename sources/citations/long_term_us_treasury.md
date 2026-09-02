# Long-Term U.S. Treasury Source Notes

Accessed: 2026-06-16

## iShares TLT

- URL: https://www.ishares.com/us/products/239454/ishares-20-year-treasury-bond-etf
- Use: target asset definition and post-inception public fund return source.
- Finding: iShares describes TLT as seeking to track an index that includes U.S. Treasury bonds with remaining maturities greater than twenty years. The page identifies the benchmark as the ICE US Treasury 20+ Year Bond Index and lists fund inception as July 22, 2002.
- Caveat: TLT is an ETF return series, not a pre-2002 long-history index.

## Yahoo Finance Chart API

- TLT endpoint: https://query1.finance.yahoo.com/v8/finance/chart/TLT
- VUSTX endpoint: https://query1.finance.yahoo.com/v8/finance/chart/VUSTX
- Use: public daily close and adjusted-close returns for the provisional fund-backed dataset.
- Finding: Yahoo returned VUSTX daily adjusted history from 1986-05-19 and TLT daily adjusted history from 2002-07-30.
- Caveat: Yahoo/yfinance data rights and terms must be reviewed before redistribution.

## Vanguard Long-Term Treasury Fund Investor Shares

- Ticker: VUSTX
- Use: public long-term Treasury mutual fund proxy before TLT daily history begins.
- Caveat: VUSTX is not the same benchmark as TLT and includes fund-specific management and expense effects.

## FRED DGS30

- URL: https://fred.stlouisfed.org/series/DGS30
- Use: candidate model input for a 30-year par-bond return extension.
- Finding: FRED identifies DGS30 as the market yield on U.S. Treasury securities at 30-year constant maturity, quoted on an investment basis, daily, sourced from the Federal Reserve H.15 release.
- Caveat: A yield series alone is not an observed total-return index. It can support a documented model-derived par-bond return extension, but coupon and price returns would be reconstructed rather than observed constituent returns.

## Federal Reserve Nominal Yield Curve

- URL: https://www.federalreserve.gov/data/nominal-yield-curve.htm
- CSV: https://www.federalreserve.gov/data/yield-curve-tables/feds200628.csv
- Use: primary model input for the pre-VUSTX 1970+ synthetic segment.
- Finding: the Federal Reserve page provides daily estimated nominal yield curve parameters and smoothed yields on hypothetical Treasury securities from 1961 to the present. The page states that the curve is based on nominal Treasury coupon securities and excludes Treasury bills and floating-rate notes; it also notes that on-the-run and first-off-the-run notes and bonds are excluded.
- Dataset use: the builder evaluates the fitted nominal zero curve at a 25-year maturity and prices a constant-maturity par Treasury bond. `Total Return` includes daily coupon carry; `Price Return` excludes coupon carry.
- Caveat: this is a Federal Reserve staff research product, not an official statistical release. The pre-VUSTX segment is model-derived, not an observed fund or constituent-level index.

## CRSP US Treasury Database

- URL: https://www.crsp.org/
- Use: preferred source for a complete 1970+ TLT-like daily dataset.
- Finding: CRSP/WRDS Treasury data is the appropriate class of source for daily Treasury issue-level prices/returns, maturities, and coupon-aware total returns back before 1970.
- Caveat: This is likely a licensed source and must be accessed through a subscription such as WRDS before implementation.
