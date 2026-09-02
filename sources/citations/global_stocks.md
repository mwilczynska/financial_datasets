# Global Stocks Source Notes

Retrieval date: 2026-06-19

## MSCI World Annual Gross Total Returns

- Finding: MSCI World has public annual gross total-return history beginning in 1970.
- Use: annual anchor for the 1970-1989 model segment.
- Caveat: annual returns are not daily observations. The build uses the project's USLCAP daily path and applies a constant within-year log-return overlay so each calendar year matches the published MSCI World gross annual return. This is model-derived and U.S.-path-biased.

## Kenneth French Developed 3 Factors Daily

- URL: https://mba.tuck.dartmouth.edu/pages/faculty/ken.french/ftp/Developed_3_Factors_Daily_CSV.zip
- Finding: daily developed-market factor file starts on 1990-07-02 and includes `Mkt-RF` and `RF`.
- Use: daily developed-market total return from `Mkt-RF + RF` until the VT observed ETF segment begins.
- Caveat: developed markets only. Emerging markets are excluded before the VT segment.

## Vanguard Total World Stock ETF / Yahoo Finance

- Ticker: `VT`
- Endpoint: https://query1.finance.yahoo.com/v8/finance/chart/VT
- Finding: Yahoo adjusted-close history begins on 2008-06-26.
- Use: observed global all-world ETF total-return segment from 2008-06-27 onward.
- Caveat: ETF net returns include expenses, sampling/tracking differences, and Yahoo adjusted-close dependence.

## Target Definition References

- MSCI ACWI and FTSE All-World are the target-style benchmarks for all-world equity exposure.
- Public daily total-return history back to 1970 for official ACWI/FTSE All-World is not available in this environment without licensing.
