# Global Short-Term Bonds (GLSTBOND) Source Notes

Retrieval date: 2026-06-21

## Target Definition

The target exposure is unhedged global SHORT-TERM (1-3yr) government bonds in USD - ISHG-like
in maturity but global in scope (it includes the US, unlike ISHG's ex-US index). Public daily
global short-government-bond history back to 1970 is not available in this environment, so the
early history is model-derived: a *direct* daily reconstruction (no annual anchor) of observed
daily FX (BIS) and a constant-maturity 2yr par bond repriced from short-end yields. From the
ISHG/BWZ inception (2009) the dataset uses an observed, GDP-weighted ETF blend.

Why no JST annual anchor (unlike GLBOND): JST's `bond_tr` is a ~10yr long-bond total return,
which is the wrong annual *level* for a 1-3yr series. Short bonds are also carry-dominated, so
the per-year overlay GLBOND needs is unnecessary here. The series is therefore built directly
from observed daily/monthly short-end data; JST contributes only GDP weights and a pre-OECD
short-rate fallback.

## Jorda-Schularick-Taylor Macrohistory Database

- URL: https://www.macrohistory.net/database/
- Finding: annual real GDP per capita (`rgdpmad`), population (`pop`), exchange rates
  (`xrusd`), and short/long rates (`stir`, `ltrate`, in percent) for 16 advanced economies.
- Use: (1) prior-year comparable-real-GDP (`rgdpmad` x `pop`) basket weights for the model
  era and the US-vs-ex-US split for the observed blend; (2) `stir`/`ltrate` interpolated to a
  2yr point as the pre-OECD fallback for the monthly yield leg. No annual return overlay.
- License caveat: JST is free for non-commercial use under its stated terms and must be cited.

## BIS Daily Exchange Rates (WS_XRU via DBnomics)

- URL: https://api.db.nomics.world/v22/series/BIS/WS_XRU/
- Finding/Use: daily local-currency-per-USD rates for all 16 countries; euro-legacy countries
  use the chained `.EUR.` series. Supplies the genuine daily currency moves of the unhedged
  path. Key-less. Identical leg to GLBOND.

## OECD MEI short and long rates (IR3TIB01, IRLTLT01 via DBnomics)

- URL: https://api.db.nomics.world/v22/series/OECD/MEI/
- Finding: monthly 3-month interbank rate (`IR3TIB01`) and 10-year government-bond yield
  (`IRLTLT01`) per country. Coverage varies (US/DEU/CAN from the 1960s; CHE `IR3TIB01` only
  from 1999, JPN from 2002), so the JST fallback fills the early gaps.
- Use: a 2-year yield is interpolated linearly in maturity between the 3-month (~0.25y) and
  10-year (~10y) rates, then a constant-maturity 2yr par bond is repriced monthly (price move
  + coupon carry) and smoothed within month for every country except the daily US/JP/UK legs.

## In-repo U.S. 1-3yr Treasury total return (STT)

- Path: data/processed/short_term_us_treasury.csv
- Use: the daily US short bond leg, 1970+ (Fed yield-curve 2yr par model -> VFISX -> SHY).

## MoF Japan historical JGB yields (2yr column)

- URL: https://www.mof.go.jp/jgbs/reference/interest_rate/data/jgbcm_all.csv
- Finding: the file (cp932, Japanese-era dates) publishes 1-9yr nodes from 1974-09-25 - the
  2yr column begins twelve years before the 10yr (which only starts 1986-07). This gives
  Japan a genuine daily short-end rate leg from 1974.
- Use: daily 2yr JGB yield repriced as a 2yr par bond with coupon carry.

## Bank of England GLC nominal daily yield curve (2yr node)

- URL: https://www.bankofengland.co.uk/-/media/boe/files/statistics/yield-curves/glcnominalddata.zip
- Finding/Use: daily 2yr nominal spot gilt yield from 1979 ("4. nominal spot curve" sheet);
  the parser selects the column nearest 2.0 years. Repriced daily as a 2yr par bond with
  coupon carry. The 39 MB archive is fetched but not committed; only the extracted 2yr series
  is persisted.

## Observed ETFs (SHY, ISHG, BWZ via Yahoo)

- SHY (iShares 1-3yr Treasury, 2002-07): US short Treasuries, adjusted-close net total return.
- ISHG (iShares 1-3yr International Treasury, 2009-01-28): developed ex-US 1-3yr sovereigns,
  unhedged. This is the named "ISHG-like" target.
- BWZ (SPDR Bloomberg Short Term International Treasury, 2009-01-30): same ex-US 1-3yr
  exposure on the Bloomberg index; averaged with ISHG to damp single-fund tracking noise.
- Use: from 2009-01-30 the observed daily return is `w_us * SHY + (1 - w_us) * mean(ISHG,
  BWZ)`, where `w_us` is the US share of developed-market real GDP that year (annually
  rebalanced, carried forward past JST's last year). The blend is net of fees (Yahoo adjusted
  close); `Close` adds a representative ~0.26%/yr fee back to stay gross.

## Modeled fees

- A representative all-in expense drag of ~0.26%/yr (actual/365) is applied: blended from SHY
  (~0.15%) and ISHG/BWZ (~0.35%) at roughly GDP weights. In the model era it is subtracted
  from the gross basket to form `Adj Close`/`Total Return`; in the observed era the ETF
  returns are already net, so the fee is added back to keep `Close`/`Price Return` gross.
  Backtesters reading `Adj Close` therefore get an investable, net-of-fee series.
