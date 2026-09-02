# Global Bonds Source Notes

Retrieval date: 2026-06-19

## Target Definition

The target exposure is unhedged global bonds in USD. Public daily global aggregate bond
history back to 1970 is not available in this environment, so the early history is
model-derived: the annual *level* is anchored to the JST database, and the within-year
*path* is reconstructed from observed daily FX (BIS) and observed monthly government-bond
yields (OECD MEI).

## Jorda-Schularick-Taylor Macrohistory Database

- URL: https://www.macrohistory.net/database/
- Finding: annual data for 18 advanced economies since 1870, including government bond total
  returns (`bond_tr`), USD exchange rates (`xrusd`, local currency per USD), real GDP per
  capita (`rgdpmad`, 1990 international dollars), population (`pop`), and nominal GDP (`gdp`).
  16 countries supply valid data every year 1970-2007.
- Use: annual level anchor + GDP weights. Each country return is converted to USD as
  `(1 + bond_tr) * previous_xrusd / current_xrusd - 1`; country weights use prior-year
  comparable real GDP (`rgdpmad` x `pop`). NB: JST's nominal `gdp` column has inconsistent
  units across countries (US in billions of USD, Spain in millions of pesetas), so `gdp /
  xrusd` is not comparable and must not be used for weights — real GDP in common
  international dollars is. Each calendar year of the early segment is rescaled by a constant
  multiplicative overlay so it compounds exactly to the JST GDP-weighted basket return.
- License caveat: JST is freely available for non-commercial use under its stated license
  terms and must be cited. Review redistribution/commercial restrictions before publishing
  derived data outside this project.

## BIS Daily Exchange Rates (`WS_XRU`, via DBnomics)

- Endpoint: https://api.db.nomics.world/v22/series/BIS/WS_XRU/D.<area>.<ccy>.A
- Finding: daily exchange rates against USD for all 16 countries; coverage back to the
  1950s-1971 (JPN 1969-12, AUS/FIN 1971-01). All series are quoted as **local currency per
  USD** (verified: JPY 357.9->146.5, GBP 0.359->0.736, EUR 2.15->0.85), matching JST's
  `xrusd` convention. Euro-legacy countries (DE/FR/IT/NL/BE/ES/FI) use the chained `.EUR.`
  series, which BIS splices through the legacy-currency era. Key-less JSON API.
- Use: genuine daily FX leg of the 1970-2007 path. Forward-filled onto the U.S. trading-day
  grid; daily USD FX return per country is `previous_fx / current_fx - 1`.
- Caveat: pre-1971 FX is fixed (Bretton Woods), so it is correctly flat there.

## OECD MEI Long-Term Interest Rates (`IRLTLT01`, via DBnomics)

- Endpoint: https://api.db.nomics.world/v22/series/OECD/MEI/<ISO3>.IRLTLT01.ST.M
- Finding: monthly 10-year government-bond yields (% per annum). Coverage from 1970 or
  earlier for 9 of 16 countries (US, Germany, UK, Canada, France, Netherlands, Switzerland,
  Belgium, Australia); Japan from 1989, Italy 1991, Spain 1980, Nordics in the 1980s.
  Key-less JSON API.
- Use: monthly rate leg of the path. A constant-maturity 10y par bond is repriced from last
  month's yield to this month's yield, plus one month of coupon carry, then smoothed across
  the month's trading days. Countries without an early yield are basket-proxied on the rate
  leg until their data begins (they still carry daily FX).
- Caveat: monthly frequency, so daily interest-rate moves before 2007 are not captured.

## Daily bond-return sources for US / Japan / UK

The three largest weights get a genuinely daily bond total return; everyone else uses the
OECD MEI monthly leg above.

- **US** — in-repo `data/processed/intermediate_term_us_treasury.csv` (Fed-yield-curve-derived
  7-10y Treasury total return), daily from 1970. ~8.5y constant maturity; the difference from
  10y is absorbed by the annual overlay.
- **Japan** — MoF historical JGB CSV: https://www.mof.go.jp/jgbs/reference/interest_rate/data/jgbcm_all.csv
  Daily 1-40y yields; the 10y column is continuous from 1986-07-05 (cp932, Japanese-era dates
  S/H/R). Repriced daily as a 10y par bond with coupon carry. Japan basket-proxied before
  1986-07. Full file cached to sources/raw.
- **UK** — BoE GLC nominal daily yield curve zip:
  https://www.bankofengland.co.uk/-/media/boe/files/statistics/yield-curves/glcnominalddata.zip
  The "4. nominal spot curve" sheet holds 0.5y-step spot yields; the 10y column runs from
  1979-01 (dates are Excel serials). Parsed manually (no openpyxl dependency). The ~39 MB
  archive is fetched at build time but not committed; only the compact extracted 10y series
  (`global_bonds_boe_gilt_10y.csv`) is persisted.

Germany was investigated as a fourth daily leg but free daily yields reach only 1997
(Bundesbank clean API; legacy codes 404; `BBIB1` is monthly bank rates), so Germany stays
monthly. Bank of Canada daily 10y starts only in 2001; RBA Australia blocks automated access.

## FRED CSV and stooq daily FX (not used)

- The FRED `fredgraph.csv` download endpoint and stooq daily-FX CSV both fail in this
  environment (connection reset / bot challenge). BIS `WS_XRU` via DBnomics was used for
  daily FX instead. The FRED API host is reachable but requires an API key.

## Vanguard Total Bond Market ETF (`BND`)

- Endpoint: https://query1.finance.yahoo.com/v8/finance/chart/BND
- Use: U.S. bond component of the observed daily segment. Caveat: U.S. aggregate bonds only.

## SPDR Bloomberg International Treasury Bond ETF (`BWX`)

- Endpoint: https://query1.finance.yahoo.com/v8/finance/chart/BWX
- Use: international unhedged bond component of the observed daily segment. Caveat:
  international sovereign bonds only; excludes international credit and securitized bonds.

## Candidate Upgrade

Licensed Bloomberg Global Aggregate unhedged daily total-return history, FTSE World
Government Bond Index total returns, or genuinely daily per-country sovereign-yield history
(not freely available back to the 1970s) would let the rate leg be daily rather than monthly.
