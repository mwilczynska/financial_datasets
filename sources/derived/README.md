# Preserved derived historical inputs

`gold_2x_historical_spot_returns.csv` retains 1,018 previously published GOLDPM
Price Return observations, 2004-11-18–2008-12-03, used by the synthetic GOLD2X
model. This includes the old GLD-stepped UK holidays, so not every observation
is an actual LBMA fixing. The adjacent JSON records original dataset and archive
hashes, coverage, creation date, and origin.

GOLDPM now follows GLD from 2004-11-18. Using its ETF returns in the leveraged
model would count GLD expenses before GOLD2X's own fee and change its historical
path. This frozen derived input preserves the existing model. It is shipped
for reproducibility; ordinary daily updates do not read it.

`broad_commodities_gsci_calendar.csv` preserves 5,255 original CMDTY observation
dates, 1970-01-02–1991-01-02. It contains dates only. The adjacent JSON records
the hash and versioned pre-migration baseline. The daily GSCI builder samples
ER/TR levels on this calendar before calculating returns, retaining growth
across skipped dates and keeping flat rows. It preserves project dates without
claiming that every source weekday is an actual futures trading session.
