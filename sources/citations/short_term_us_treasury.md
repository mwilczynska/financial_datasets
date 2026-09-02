# Short-Term U.S. Treasury Source Notes

Accessed: 2026-06-16

## iShares SHY

- URL: https://www.ishares.com/us/products/239452/ishares-13-year-treasury-bond-etf
- Use: target asset definition and post-inception public fund return source.
- Finding: iShares describes SHY as seeking to track an index that includes U.S. Treasury bonds with remaining maturities between 1 and 3 years. The benchmark is the ICE US Treasury 1-3 Year Bond Index.
- Caveat: SHY is an ETF return series and does not provide pre-2002 history.

## Yahoo Finance Chart API

- SHY endpoint: https://query1.finance.yahoo.com/v8/finance/chart/SHY
- VFISX endpoint: https://query1.finance.yahoo.com/v8/finance/chart/VFISX
- Use: public daily close and adjusted-close returns for the fund-backed dataset.
- Finding: Yahoo returned VFISX daily adjusted history from late October 1991 and SHY daily adjusted history from late July 2002.
- Caveat: Yahoo/yfinance data rights and terms must be reviewed before redistribution.

## Vanguard Short-Term Treasury Fund Investor Shares

- Ticker: VFISX
- Use: public short-term Treasury mutual fund proxy before SHY daily history begins.
- Finding: VFISX primarily holds U.S. government bonds with short-term maturities. Yahoo chart data covers from approximately 1991-10-29.
- Caveat: VFISX is not the same benchmark as SHY and includes fund-specific management and expense effects. Its maturity/duration profile may differ from SHY's at any given date.

## Federal Reserve Nominal Yield Curve

- URL: https://www.federalreserve.gov/data/nominal-yield-curve.htm
- CSV: https://www.federalreserve.gov/data/yield-curve-tables/feds200628.csv
- Use: primary model input for the pre-VFISX 1970+ synthetic segment.
- Finding: the Federal Reserve page provides daily estimated nominal yield curve parameters and smoothed yields on hypothetical Treasury securities from 1961 to the present. The page states that the curve is based on nominal Treasury coupon securities and excludes Treasury bills and floating-rate notes; on-the-run and first-off-the-run notes and bonds are also excluded.
- Dataset use: the builder evaluates the fitted nominal zero curve at a 2-year maturity (midpoint of the 1-3 year SHY target band) and prices a constant-maturity par Treasury bond. `Total Return` includes daily coupon carry; `Price Return` excludes coupon carry.
- Caveat: this is a Federal Reserve staff research product, not an official statistical release. The pre-VFISX segment is model-derived, not an observed fund or constituent-level index.

## CRSP US Treasury Database

- URL: https://www.crsp.org/
- Use: preferred source for a complete 1970+ SHY-like daily dataset.
- Finding: CRSP/WRDS Treasury data is the appropriate class of source for daily Treasury issue-level prices/returns, maturities, and coupon-aware total returns back before 1970.
- Caveat: this is a licensed source and must be accessed through a subscription such as WRDS before implementation.
