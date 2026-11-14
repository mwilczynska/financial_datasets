# FX Rate Source Notes (AUDUSD, EURUSD, GBPUSD)

Retrieval date: 2026-11-14

Content hashes, observed coverage and observation counts for each downloaded
file are recorded under `historical_sources` in
`sources/manifests/fx_*_build.json`. Raw downloads stay in ignored `sources/raw/`.

## BIS bilateral exchange rates, WS_XRU

- API: https://stats.bis.org/api/v2/data/dataflow/BIS/WS_XRU/1.0/D.<area>.<currency>.A (SDMX CSV)
- Topic page: https://data.bis.org/topics/XRU
- Series used: `D.AU.AUD.A`, `D.DE.EUR.A`, `D.GB.GBP.A` (daily, local currency per USD, "average of observations through period").
- Observed coverage on 2026-11-14: GBP from 1953-08-10, German series from 1953-09-01, AUD from 1971-01-04; all through 2026-11-10. The datasets use 1970-01-02 to 1998-12-31 and fetch through 1999-12-31 for the splice check.
- Non-observation days are present as `NaN` with status `M`; they are dropped.
- Retrieval finding: requests for a whole series returned HTTP 200 but ended early (for example the GBP response stopped in 1959). Decade-long requests completed in seconds. The builder therefore fetches by decade and rejects a chunk that does not span its requested range.
- Vendor statements (topic page, read 2026-11-14): the ECB is the primary source of daily data for recent periods, complemented by the U.S. Federal Reserve and other member central banks; the Bundesbank and IMF International Financial Statistics are main historical sources; ECB rates are measured at 13:15 GMT; data are released weekly.
- Verified observation: at six decimals the BIS AUD series equals the ECB USD/EUR over AUD/EUR cross on all 7,133 common days from 1999-01-04 to 2026-11-10. The 1999 overlap check in the builder gives a maximum relative difference of 3.3e-7 (AUD), 5.7e-7 (EUR) and 8.0e-7 (GBP).
- The DBnomics mirror used by GLBOND for the same data ended on 2025-07-08 when checked on 2026-11-14, so it is not used here.
- Terms (https://data.bis.org/help/legal, read 2026-11-14): use of the statistics is unrestricted provided the BIS is cited as the source, use is not misleading and does not imply endorsement, and commercial use does not result in an additional charge to subscribers or other users. https://www.bis.org/terms_statistics.htm returned HTTP 403 and was not read.
- Unresolved: fixing time and upstream source of each pre-1999 daily observation; the construction of the separate euro-area series (`D.XM.EUR.A`, from 1974-06-28), which is not used.
- Attribution: Bank for International Settlements, bilateral exchange rates (WS_XRU).

## ECB euro foreign exchange reference rates

- File: https://www.ecb.europa.eu/stats/eurofxref/eurofxref-hist.zip (single member `eurofxref-hist.csv`, newest row first, `N/A` for unpublished currencies).
- Information page: https://www.ecb.europa.eu/stats/policy_and_exchange_rates/euro_reference_exchange_rates/html/index.en.html
- Observed coverage on 2026-11-14: 1999-01-04 through 2026-11-13; USD, GBP and AUD columns present.
- Use: every row from 1999-01-04 and every daily update. EURUSD is the published USD rate; AUDUSD and GBPUSD are the USD rate divided by the AUD or GBP rate.
- Vendor statements (information page, read through a page summary on 2026-11-14, not verbatim): rates are usually updated around 16:00 CET on working days except TARGET closing days and are published for information purposes only.
- Terms (https://www.ecb.europa.eu/services/disclaimer/html/index.en.html, read through a page summary, not verbatim): free use is permitted subject to conditions, including that the ECB is cited as the source and modifications are stated. The crosses published here are a modification and are labeled as such in each row.
- Unresolved: the exact reuse wording should be confirmed against the disclaimer page before commercial redistribution.
- Attribution: European Central Bank, euro foreign exchange reference rates.

## Not used

- FRED H.10 daily series (`DEXUSAL`, `DEXUSUK`, `DEXUSEU`): the download failed with a connection error on 2026-11-14, consistent with the earlier GLBOND finding. Not evaluated.
- RBA historical exchange rates: https://www.rba.gov.au/statistics/tables/csv/f11.1-data.csv returned HTTP 403 to a scripted request on 2026-11-14. Not evaluated.
- BIS monthly AUD (`M.AU.AUD.A`): shows the official par of 0.892857 AUD per USD (USD 1.12) for every month of 1970. It confirms the peg but gives no daily path.
