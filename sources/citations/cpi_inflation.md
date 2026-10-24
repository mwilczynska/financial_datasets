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
- Use: validation/reference source and an independently hosted delivery fallback when the BLS API has a transient outage.
- Download: https://fred.stlouisfed.org/graph/fredgraph.csv?id=CPIAUCSL
- Alternate delivery: https://fred.stlouisfed.org/data/CPIAUCSL when the CSV route has a transient transport/HTTP failure. The table must explicitly identify the BLS source, CPIAUCSL series, monthly frequency, seasonally adjusted definition, and index units before its observations are accepted. Both FRED routes use one retry with bounded connection/read timeouts.
- Recovery change (2026-10-24): the incremental updater may use a freshly downloaded FRED response after BLS connection/time-out errors, exhausted retries, or HTTP 429/500/502/503/504. A malformed BLS response or non-transient HTTP error still fails immediately.
- Validation: require the latest committed monthly anchor and at least three committed monthly observations in the downloaded window. Every overlapping monthly value must match within 1e-9, with exactly the same observed-month coverage. Existing unpublished months, including October 2025, remain interpolated; missing committed observations and gaps among new monthly observations are rejected. Wrong series, nonpositive/nonfinite levels, and observations older than 90 days are rejected. The publication gate rechecks the raw response hash, provider, series, coverage, retrieval timestamp, and overlap independently.
- Attribution: U.S. Bureau of Labor Statistics, Consumer Price Index for All Urban Consumers: All Items in U.S. City Average [CPIAUCSL], retrieved from FRED, Federal Reserve Bank of St. Louis.
- The fallback changes delivery, while retaining the seasonally adjusted BLS series, units, daily expansion, quality flags, and historical output contract. Both sources being unavailable blocks publication.
