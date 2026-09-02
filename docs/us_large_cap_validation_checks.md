# U.S. Large-Cap Validation Checks

Run date: 2026-06-16

## Daily Source Integrity: 1970-1987

Checked `USLCAP.Total Return` against the raw Kenneth French Data Library / CRSP `Hi 30` value-weighted daily returns.

- Period checked: after `1970-01-02` through `1987-12-31`
- Rows checked: 4,548
- Missing French source rows: 0
- Maximum absolute difference: approximately `6.94e-18`

Result: pass. The pre-`^SP500TR` daily total-return column matches the raw French daily source to floating-point precision.

## External Annual Sanity Check: 1970-1987

Compared calendar-year compounded `USLCAP.Adj Close` returns against an external S&P 500 total-return annual table.

Reference used: https://en.wikipedia.org/wiki/S%26P_500

This is an independent reasonableness check, not an exact-match test. Pre-1988 `USLCAP` uses the CRSP/French large-cap `Hi 30` portfolio as a daily U.S. large-cap/blend proxy, while the reference table reports S&P 500 total annual return including dividends.

Summary:

- Years checked: 18
- Mean absolute difference: 1.57 percentage points
- Maximum absolute difference: 4.79 percentage points
- Worst year: 1975

| Year | USLCAP TR | S&P 500 TR Ref | Difference, pp |
| --- | ---: | ---: | ---: |
| 1970 | 1.82% | 4.01% | -2.19 |
| 1971 | 16.21% | 14.31% | 1.90 |
| 1972 | 19.46% | 18.98% | 0.48 |
| 1973 | -15.64% | -14.66% | -0.98 |
| 1974 | -27.61% | -26.47% | -1.14 |
| 1975 | 32.41% | 37.20% | -4.79 |
| 1976 | 22.52% | 23.84% | -1.32 |
| 1977 | -6.84% | -7.18% | 0.34 |
| 1978 | 7.56% | 6.56% | 1.00 |
| 1979 | 18.21% | 18.44% | -0.23 |
| 1980 | 35.44% | 32.50% | 2.94 |
| 1981 | -5.58% | -4.92% | -0.66 |
| 1982 | 19.28% | 21.55% | -2.27 |
| 1983 | 22.32% | 22.56% | -0.24 |
| 1984 | 8.06% | 6.27% | 1.79 |
| 1985 | 34.09% | 31.73% | 2.36 |
| 1986 | 19.08% | 18.67% | 0.41 |
| 1987 | 1.95% | 5.25% | -3.30 |

Interpretation: pass as a proxy sanity check. Differences are expected because pre-1988 adjusted data is a CRSP large-cap/blend proxy, not official S&P 500 total return.
