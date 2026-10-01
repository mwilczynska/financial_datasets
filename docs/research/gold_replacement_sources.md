# Free daily gold source evaluation

Decision following this evaluation: the user selected GLD from its first
available quote, 2004-11-18. The observed price column is now a scaled ETF index;
the original spot-fixing requirement no longer applies to that segment. See
[migration results](../operations/2026-09-30-gld-migration.md) and
[current methodology](../methodology_goldpm.md). Candidate observations below
describe the initial search for a replacement spot feed.

Evaluated on 2026-09-30 following the GOLDPM refresh failure. Free daily gold
prices are available. The next candidate to trial is Gold-API.com's free
historical tier. No replacement has yet passed the complete production
acceptance checks, and no processed dataset was changed.

The requirement is a reproducible daily USD-per-troy-ounce price with a dated
history, suitable for unattended catch-up and overlap validation. A current live
quote alone cannot recover missed days. This repository also publishes its
processed CSV and Parquet outputs, so public redistribution matters separately
from free access or permission to display a widget.

## Candidate findings

| Source | Free access and observed result | Price definition and suitability |
|---|---|---|
| [Gold-API.com](https://gold-api.com/llms.txt) | Live XAU request succeeded. Historical request without a key returned 401, as expected. Published free plan includes 10 history/OHLC requests per hour with a free key. | First candidate to trial. History supports daily max/min/average aggregates; OHLC returns a close over a specified time range. Do not label a daily average as a daily close. Historical coverage, source provenance, finalization, and export permission need validation. |
| [fawazahmed0 currency-api](https://github.com/fawazahmed0/exchange-api) | Anonymous, dated XAU/USD requests for September 25, 28, and 29 succeeded; latest returned September 30. Repository advertises daily updates, no rate limits, and CC0. | Best anonymous secondary reference among the tested candidates. These are daily publication snapshots, not a documented London PM fixing or market close. Generator stamps the build date and reads upstream URLs from environment variables; upstream quote time and licensing were not established. Repository CC0 does not itself establish rights in upstream prices. |
| [NBP public API](https://api.nbp.pl/en.html) | Gold and USD/PLN requests each returned 65 observations from July 1 through September 29. Documented gold history begins January 2, 2013, with at most 93 days per query. | Credible official calculated gold-price reference. Gold is quoted per gram in PLN; USD reconstruction adds exchange-rate and observation-date assumptions. Suitable for further reference-source research, not a verified USD PM replacement. |
| [Standard Bullion](https://standardbullion.com/gold-price-api) | Anonymous request returned 324 daily observations from September 30, 2025 through September 29, 2026. Provider advertises daily coverage from 2011. | Current dealer price, with older history assembled from LBMA/USGS. Returned series omitted September 14–18, 2026. Provider permits commercial display with attribution but excludes bulk redistribution of its raw feed. Not selected for this public dataset. |
| [goldprice.dev](https://goldprice.dev/docs/historical) | Anonymous daily-bar request for September 1–29 returned 14 bars, of which 13 were marked completed. Earliest completed bar was September 4; latest was September 29. Free history is documented as a rolling 30-day window. | UTC daily spot bars with an explicit `is_closed` field are useful in principle. The tested window had missing gold trading dates. Its [terms](https://goldprice.dev/terms) prohibit third-party redistribution on the free tier. Not selected. |
| [Stooq XAUUSD](https://stooq.com/q/d/?s=xauusd) | Both the web page and the requested daily CSV returned a browser-verification response rather than usable prices. | A spot candidate if supported automated access becomes available; not operationally usable in the tested environment. No browser challenge was bypassed. |
| [Dukascopy historical data](https://www.dukascopy.com/swiss/english/marketwatch/historical/) | The legacy 2026 bid daily-candle URL returned 404; the ask request timed out. Those tests do not establish that all Dukascopy delivery methods are unavailable. | Broker spot quotes could supply a defined daily cutoff. Current [export documentation](https://www.dukascopy.com/wiki/en/development/data-export/) describes an AWS Requester Pays route. Website [terms](https://www.dukascopy.com/swiss/english/legal-pages/terms-of-use/) restrict database construction and automation; a suitable data-feed agreement remains unverified. Not the immediate free public-dataset choice. |
| [SPDR GLD issuer archive](https://www.spdrgoldshares.com/usa/gld/) | Public page succeeded and exposes a historical XLSX archive. The workbook was not downloaded or analyzed after reviewing the access terms. | Potentially the closest technical match because GLD uses LBMA PM for valuation. [Terms](https://www.spdrgoldshares.com/terms-and-conditions/) limit use and specifically restrict disclosure of LBMA price information. The public download is not an open redistribution licence. |
| Yahoo `XAUUSD=X` / `GC=F` | Spot ticker request returned 404. Futures request succeeded with 63 observations from July 1 through September 29; metadata identified the instrument as `FUTURE`. | `GC=F` is futures rather than spot. Its contract basis and rolls need a separate futures methodology. It is not a replacement fixing just because it is a daily gold price. |
| World Gold Council / DBnomics LBMA | [WGC](https://www.gold.org/goldhub/data/gold-prices) states that historical LBMA data was removed at IBA's request in March 2025. The tested DBnomics `LBMA/gold_D/USD-PM` API returned 404. | These were not usable free current mirrors of the exact fixing. |
| [FreeGoldAPI.com](https://freegoldapi.com/) | Website documentation reviewed; endpoint was not probed. | Its modern daily source is Yahoo `GC=F`, preceded by monthly/annual sources. It does not independently solve the spot-price requirement or provide centuries of daily prices. |

Gold-API.com's [pricing](https://gold-api.com/pricing) advertises the free
historical allowance. Its [terms](https://gold-api.com/terms) permit commercial
API use, including applications and websites. They do not explicitly settle
whether a bulk downloadable public CSV can contain the provider's historical
prices; that remains an unresolved constraint, not a verified prohibition.

## Measured differences

Compared downloaded candidates with the local committed GOLDPM `Close` from
July 1 through September 25, 2026, including its documented UK-holiday proxy
rows. The local checkout's last observation is September 25; the remote
production baseline cited in the incident note is newer. No comparison here
claims to cover the remote September 28 row.

| Candidate / window | Common observations | Median absolute price difference | Maximum absolute difference | Return correlation |
|---|---:|---:|---:|---:|
| Standard Bullion, July 1–September 25 | 56 | 0.233% | 2.289% | 0.814 |
| goldprice.dev, September 1–25 | 9 | 0.495% | 1.302% | 0.895 |
| NBP converted using same-publication-date USD/PLN, July 1–September 25 | 61 | 0.818% | 3.405% | 0.259 |

Returns were computed between consecutive common dates. Where observations are
missing, an interval can span multiple trading days; the correlations are not
all correlations of one-day returns and the sample lengths differ. They do not
establish which vendor is more accurate. Price timing, bid/ask treatment, and
benchmark definition can explain differences.

The NBP conversion was exploratory:

`USD/oz = PLN/gram × 31.1034768 / USDPLN`.

Using FX and gold values with the same publication date does not prove their
underlying observation times align. The weak return correlation means that
naive conversion is unsuitable for direct adoption without investigating lag
and fixing definitions.

## Original spot-source trial proposal (superseded by GLD selection)

1. Obtain a free Gold-API.com key and configure it as a local secret and, when
   integration is ready, a GitHub Actions secret. No account was created or key
   obtained during this evaluation.
2. Retrieve historical data for a completed overlap and verify positive finite
   prices, unique ordered dates, complete required trading dates, UTC bounds,
   end-of-day finalization, repeatability, and revisions. Compare against both
   existing GOLDPM and the dated currency-api reference. Confirm provider and
   export permissions for the public processed dataset.
3. Choose the daily statistic explicitly. The batched history endpoint's daily
   average needs one request for an overlap but changes the price definition.
   Per-day OHLC queries can supply closes but consume the 10-request/hour
   allowance rapidly when reconstructing the existing overlap and publication
   checks. Test that request budget before choosing a close adapter; do not
   assume the free tier supports an arbitrary historical catch-up in one run.
4. Keep historical data fixed and introduce a documented source transition only
   after a trial passes. A replacement quote has its own timestamp and basis.
   Preserve the USD/oz meaning of raw prices and assess the transition-day
   return; a rescaled index should be labelled as a proxy rather than an
   observed dollar price.
5. Keep GLD adjusted-close returns for GOLDPM's modern `Adj Close` and
   `Total Return`. Changing only modern spot `Close` does not require changing
   that GLD tracking. GOLD2X uses observed UGL in the modern segment; rebuilding
   modeled historical segments is a separate decision.
6. Update provenance, quality flags, manifests, source parsing, publication
   checks, and gold contract tests together. Select one persistent daily price
   definition; use independent sources for validation rather than switching
   between incompatible quote times on every outage.

This is a recommendation to trial a free source, not a claim that a validated
replacement is already ready to publish. Paid LBMA access is unnecessary if an
acceptable alternative daily spot definition and suitable source terms are
established.

## Reproducibility

Downloaded responses are local caches under
`sources/raw/gold_source_evaluation_2026_09_30/`. The retrieval manifest records
URLs, UTC access timestamps, response status, SHA-256 hashes, observed coverage,
and unresolved constraints. Exploratory normalized observations and comparison
results are under `data/interim/gold_source_evaluation/`. No source raw files or
candidate prices were added to production outputs, and commodities research
was not modified.
