# U.S. Large-Cap Equity / S&P 500 Source Notes

Accessed: 2026-06-16

## S&P Dow Jones Indices

- URL: https://www.spglobal.com/spdji/en/indices/equity/sp-500/
- Use: authoritative description and methodology reference.
- Finding: S&P DJI describes the S&P 500 as a large-cap U.S. equity gauge with 500 leading companies and about 80% coverage of available market capitalization.
- Caveat: review licensing before storing or redistributing index history.

## FRED `SP500`

- URL: https://fred.stlouisfed.org/series/SP500
- Use: independent validation source for recent daily close levels.
- Finding: daily close index values sourced from S&P Dow Jones Indices.
- Caveat: FRED states the series is a price index and does not contain dividends. FRED also notes its agreement includes 10 years of daily history for S&P and Dow Jones series.

## Yahoo Finance / yfinance

- URL: https://pypi.org/project/yfinance/
- Chart endpoint used for initial build: https://query1.finance.yahoo.com/v8/finance/chart/%5EGSPC
- Total-return chart endpoint used for adjusted data after available history begins: https://query1.finance.yahoo.com/v8/finance/chart/%5ESP500TR
- Use: compatibility reference for Yahoo-style pandas dataframes and possible recent-market data source.
- Finding: yfinance provides a Python interface for Yahoo Finance-style data.
- Caveat: yfinance states it is not affiliated with, endorsed by, or vetted by Yahoo, and points users to Yahoo terms of use for data rights.
- Dataset caveat: `^GSPC` is an index-level price series. Its adjusted close output must not be interpreted as a true dividend-reinvested total-return series. Yahoo `^SP500TR` daily data starts in 1988 in the chart endpoint checked on 2026-06-16.

## Kenneth French Data Library / CRSP Size Portfolios

- URL: https://mba.tuck.dartmouth.edu/pages/faculty/ken.french/ftp/Portfolios_Formed_on_ME_daily_CSV.zip
- Data Library page: https://mba.tuck.dartmouth.edu/pages/faculty/ken.french/data_library.html
- Use: daily U.S. large-cap/blend total-return source before Yahoo `^SP500TR` can supply daily returns.
- Finding: the file states it is created using the CRSP database and contains value- and equal-weighted returns for size portfolios. The `Hi 30` value-weighted portfolio is used as the large-cap total-return proxy.
- Caveat: this is not the official S&P 500 total-return index. It is a daily CRSP-based U.S. large-cap/blend proxy.

## Portfolio Visualizer Asset-Class Data Sources

- URL: https://www.portfoliovisualizer.com/faq#marketData
- Use: candidate reference for future asset-class data-source choices.
- Finding: user identified this FAQ section as useful for asset-class return source references.
- Caveat: use as a reference unless direct downloadable data access, reproducibility, and terms are confirmed.

## Bogleheads Simba's Backtesting Spreadsheet

- URL: https://www.bogleheads.org/wiki/Simba%27s_backtesting_spreadsheet
- Use: candidate reference for future asset-class data-source choices.
- Finding: user identified this page as potentially useful for data-source references.
- Caveat: direct fetch returned `403 Forbidden` on 2026-06-16. It is likely annual-return oriented, so do not use it as a daily raw data source without verifying linked sources independently.

## Robert Shiller Data

- URL: https://www.econ.yale.edu/~shiller/data.htm
- Use: rejected for the current USLCAP adjusted-series requirement.
- Finding: data is useful for long-run equity research, but the current requirement is daily total-return data without estimates.
- Caveat: monthly data cannot be used to create this daily adjusted series.
