# Gold Source Notes

Accessed: 2026-06-16; revised 2026-06-20 (redefined to track GLD including fees).

## Dataset intent

`GOLDPM` is built to behave like holding the SPDR Gold Shares ETF (`GLD`), **including its fee
drag**, extended back to 1970. `Close` stays pure LBMA PM spot; `Adj Close` is GLD-tracking
(spot minus 0.40% expense drag pre-2004, then observed GLD).

## LBMA Gold Price PM

- URL: https://prices.lbma.org.uk/json/gold_pm.json
- Public page: https://www.lbma.org.uk/prices-and-data/precious-metal-prices
- Use: drives `Close` / `Price Return` (pure spot) across all of 1970-present, and the modeled
  `Adj Close` (spot minus GLD expense drag) before GLD's 2004 inception.
- Finding: LBMA provides daily Gold PM fixing data back to 1968. The JSON values include USD per troy ounce as the first value.
- Caveat: this is a spot/fixing price series struck at the London PM fix (~10am ET), not the US
  4pm close. It excludes storage, insurance, financing, taxes, transaction costs, and futures
  collateral yield.

## SPDR Gold Shares (GLD) — Yahoo chart API

- URL: https://query1.finance.yahoo.com/v8/finance/chart/GLD
- Use: drives `Adj Close` / `Total Return` from 2004-11-19 onward; `Adj Close` is exactly
  proportional to GLD's adjusted close in this era (the modern series *is* GLD).
- Finding: GLD inception 2004-11-18; adjusted close reflects the fund's gold-per-share erosion
  from its 0.40% expense ratio. Over 2004-2026 GLD underperformed pure spot by ~0.49%/yr (mostly
  the fee), which is exactly the drag this dataset now folds in.
- Caveat: GLD closes at 4pm ET vs the LBMA PM fix; day-to-day timing differs but is zero-mean for
  cumulative return.
- Calendar: the observed era is built on **GLD's (NYSE) trading calendar**, not the London/LBMA
  calendar. This is essential because the project backtester compares series by intersecting daily
  returns and compounding; a London-calendar gold series vs a US-calendar ETF drifts on every
  UK-bank-holiday day (it produced a spurious +47% cumulative GOLDPM-vs-GLD gap over 2004-2026
  even though the levels were proportional). On UK bank holidays (no LBMA fix) Close is stepped by
  GLD's move so the series stays on GLD's calendar without inventing a London fixing.

## LBMA Gold Price AM

- URL: https://prices.lbma.org.uk/json/gold_am.json
- Use: same-administrator sanity reference.
- Caveat: this is not an independent source from LBMA PM, but it can help detect gross data problems.

## FRED Gold PM

- URL: https://fred.stlouisfed.org/series/GOLDPMGBD228NLBM
- Use: candidate validation source for the same London PM gold price.
- Finding: FRED requires an API key for metadata API access; graph CSV timed out in this environment during initial implementation.
- Caveat: source appears to mirror London PM fixing data, so it is not methodologically independent from LBMA.
