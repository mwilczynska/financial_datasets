# Intermediate-Term U.S. Treasury Source Notes

Accessed: 2026-06-16

## iShares IEF

- URL: https://www.ishares.com/us/products/239456/ishares-710-year-treasury-bond-etf
- Use: target asset definition and post-inception public fund return source.
- Finding: iShares describes IEF as seeking to track an index that includes U.S. Treasury bonds with remaining maturities between 7 and 10 years. The benchmark is the ICE US Treasury 7-10 Year Bond Index.
- Caveat: IEF is an ETF return series and does not provide pre-2002 history.

## Yahoo Finance Chart API

- IEF endpoint: https://query1.finance.yahoo.com/v8/finance/chart/IEF
- VFITX endpoint: https://query1.finance.yahoo.com/v8/finance/chart/VFITX
- Use: public daily close and adjusted-close returns for the fund-backed dataset.
- Finding: Yahoo returned VFITX daily adjusted history from late October 1991 and IEF daily adjusted history from late July 2002.
- Caveat: Yahoo/yfinance data rights and terms must be reviewed before redistribution.

## Vanguard Intermediate-Term Treasury Fund Investor Shares

- Ticker: VFITX
- Use: public intermediate-term Treasury mutual fund proxy before IEF daily history begins.
- Finding: VFITX primarily holds U.S. government bonds with intermediate-term maturities. Yahoo chart data covers from approximately 1991-10-29.
- Caveat: VFITX is not the same benchmark as IEF and includes fund-specific management and expense effects. Its maturity/duration profile may differ from IEF's at any given date.

## Federal Reserve Nominal Yield Curve

- URL: https://www.federalreserve.gov/data/nominal-yield-curve.htm
- CSV: https://www.federalreserve.gov/data/yield-curve-tables/feds200628.csv
- Use: primary model input for the pre-VFITX 1970+ synthetic segment.
- Finding: the Federal Reserve page provides daily estimated nominal yield curve parameters and smoothed yields on hypothetical Treasury securities from 1961 to the present. The page states that the curve is based on nominal Treasury coupon securities and excludes Treasury bills and floating-rate notes; on-the-run and first-off-the-run notes and bonds are also excluded.
- Dataset use: the builder evaluates the fitted nominal zero curve at an 8.5-year maturity (midpoint of the 7-10 year IEF target band) and prices a constant-maturity par Treasury bond. `Total Return` includes daily coupon carry; `Price Return` excludes coupon carry.
- Caveat: this is a Federal Reserve staff research product, not an official statistical release. The pre-VFITX segment is model-derived, not an observed fund or constituent-level index.

## CRSP US Treasury Database

- URL: https://www.crsp.org/
- Use: preferred source for a complete 1970+ IEF-like daily dataset.
- Finding: CRSP/WRDS Treasury data is the appropriate class of source for daily Treasury issue-level prices/returns, maturities, and coupon-aware total returns back before 1970.
- Caveat: this is a licensed source and must be accessed through a subscription such as WRDS before implementation.
