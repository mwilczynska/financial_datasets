# Gold source notes

Revised 2026-09-30: GLD adopted from its earliest daily quote, 2004-11-18.

- Yahoo chart: https://query1.finance.yahoo.com/v8/finance/chart/GLD
- Issuer: https://www.ssga.com/us/en/individual/etfs/spdr-gold-shares-gld
- Original historical LBMA: https://prices.lbma.org.uk/json/gold_pm.json

The full Yahoo request from 2004-01-01 through 2026-09-29 returned 5,499 usable
close/adjusted-close observations, beginning 2004-11-18. Retrieval dates, coverage,
and hashes are in gold build metadata and the ignored source retrieval manifest
under `sources/raw/gld_switch_2026_09_30/`. The chart is cached locally as
`sources/raw/gold_yahoo_gld_chart.json`.

The issuer reports inception 2004-11-18 and 0.40% expenses. Expenses reduce gold
represented per share. GLD prices can differ from NAV and have US-close timing;
scaled prices are indices rather than exact USD/oz spot quotes. No additional
GLD expense is deducted from observed returns.

Published 1970-01-02–2004-11-17 rows remain unchanged: historical spot Close and
modeled expense-adjusted returns. Both GLD indices anchor to the preceding
modeled levels with zero first-quote return, then follow GLD on its NYSE calendar.
Pre-inception history is a model. LBMA's current 403 no longer blocks ordinary
updates; explicit historical LBMA refresh still requires source access.

GOLD2X retains historical spot inputs via
`sources/derived/gold_2x_historical_spot_returns.csv` and its provenance JSON.
These preserved published inputs include the old GLD-stepped UK holidays.

Yahoo access/redistribution rights remain unresolved. An open-source client
does not license its data: https://github.com/ranaroussi/yfinance
