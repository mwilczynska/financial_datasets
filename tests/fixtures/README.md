# Validation Fixtures

Store small independent-source fixtures here when licensing permits.

Large or restricted source files should not be committed here. Use manifests under `sources/manifests/` to describe external files that must be retrieved separately.

Current fixtures:

- `fred_sp500_sample.csv`: small hand-recorded recent FRED `SP500` close-level sample used to validate the initial Yahoo `^GSPC` output. Values were taken from the FRED series page on 2026-06-16.
- `us_large_cap_annual_check_1970_1987.csv`: annual USLCAP adjusted-return comparison against an external S&P 500 total-return reference table. This is a sanity check only because pre-1988 USLCAP uses a CRSP large-cap proxy, not official S&P 500 total return.
