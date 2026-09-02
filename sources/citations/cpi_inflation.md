# CPI Inflation Source Notes

Retrieval date: 2026-06-19

## BLS CPI-U, CUSR0000SA0

- URL: https://api.bls.gov/publicAPI/v2/timeseries/data/
- Series: `CUSR0000SA0`
- Finding: monthly U.S. CPI-U, all urban consumers, U.S. city average, all items, seasonally adjusted, index 1982-84=100.
- Use: primary monthly CPI source. The processed dataset expands this monthly index to calendar-daily rows by constant log interpolation between adjacent monthly observations.
- Caveat: BLS does not publish observed daily CPI. Daily rows between monthly observations are model-derived and should be used only as a smooth deflator for daily portfolio levels.

## FRED CPIAUCSL

- URL: https://fred.stlouisfed.org/series/CPIAUCSL
- Finding: same CPI-U concept published by FRED.
- Use: validation/reference source.
- Caveat: direct FRED CSV retrieval timed out during this build, so BLS is the active source.
