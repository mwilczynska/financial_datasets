# GLBOND - Unhedged Global Bonds

Dataset identifier: `global_bonds`

Backtest alias: `GLBOND`

Status: complete model-derived public-source proxy

## Asset Definition

`GLBOND` is an unhedged global bond total-return proxy in USD. The early segment is a
developed-market government-bond basket; the observed segment blends U.S. aggregate bonds
with unhedged international treasury bonds.

- `Close`: normalized total-return proxy level.
- `Adj Close`: equal to `Close`.
- `Price Return` and `Total Return`: equal daily total-return proxy.

This dataset intentionally does not hedge currency exposure.

## Output Files

| File | Path |
|---|---|
| CSV | `data/processed/global_bonds.csv` |
| Parquet | `data/processed/global_bonds.parquet` |
| Manifest | `sources/manifests/global_bonds.yml` |
| Citation notes | `sources/citations/global_bonds.md` |
| Build script | `src/build_global_bonds.py` |
| Update script | `src/update_global_bonds.py` |
| Test file | `tests/validation/test_global_bonds_contract.py` |

Coverage starts on `1970-01-02`.

## Source Chain

| Segment | Dates | Source | Quality flag |
|---|---|---|---|
| JST-anchored daily reconstruction | 1970-01-02 to 2007-10-10 | JST annual basket (anchor) + BIS daily FX + daily bond TR for US/JP/UK + OECD MEI monthly yields for the rest | `model_jst_anchored_daily_fx_monthly_yield_global_govt_bond_unhedged` |
| Observed daily unhedged proxy | 2007-10-12 onward | 45% BND + 55% BWX adjusted-close returns | `observed_bnd_bwx_unhedged_daily_rebalanced_proxy` |

Daily bond-return sources for the three largest weights (≈62% of the basket from 1979):

| Country | Daily bond source | Daily from |
|---|---|---|
| US | in-repo 7-10y Treasury total return (`intermediate_term_us_treasury.csv`) | 1970-01 |
| Japan | MoF daily 10y JGB yield (`jgbcm_all.csv`) | 1986-07 |
| UK | BoE GLC daily 10y nominal spot yield | 1979-01 |

All other countries, and US/JP/UK before their daily-yield start, use the OECD MEI monthly rate leg.

## Build Method

The early segment reconstructs a daily total-return **path** from observed data, then
rescales each calendar year so it matches the authoritative JST annual basket. JST
supplies the annual *level* anchor; the FX + yield reconstruction supplies the within-year
*path*. This is the same "realistic shape + annual anchor" technique used by `GLSTOCK`.

1. **Annual anchor + weights (JST).** For each country/year with valid data, compute the
   unhedged USD government-bond return
   `usd_return = (1 + local_bond_return) * previous_xrusd / current_xrusd - 1`
   (`xrusd` is local currency per USD), weight by prior-year comparable real GDP
   (`rgdpmad` real GDP per capita in 1990 international dollars x `pop`), and form the
   GDP-weighted annual basket return and per-country weights for each year (`jst_basket`).
   16 advanced economies contribute every year 1970-2007. (Real GDP is used because JST's
   nominal `gdp` column has inconsistent units across countries, so `gdp / xrusd` is not
   comparable and badly mis-weights the basket toward small economies.)
2. **Daily FX leg (BIS).** Fetch BIS `WS_XRU` daily exchange rates (local currency per USD)
   for all 16 countries via DBnomics. For euro-legacy countries the chained `.EUR.` series
   is used (BIS splices the legacy currency into the euro series), reaching back to the
   1950s-1971. Forward-fill onto the trading-day grid and compute genuine daily USD FX
   returns per country (`previous_fx / current_fx - 1`; the U.S. leg is 1.0).
3. **Rate leg.** Two tiers:
   - *Daily (US, Japan, UK).* Use a genuine daily bond total return for the three largest
     weights: the in-repo 7-10y U.S. Treasury total return (1970+), and a constant-maturity
     10y par bond repriced day-to-day from the MoF daily 10y JGB yield (1986-07+) and the BoE
     daily 10y nominal spot yield (1979+), each with actual-day coupon carry
     (`daily_bond_returns_from_yields`). National yields are forward-filled onto the trading
     grid, so a day the market did not move carries only.
   - *Monthly (everyone else, and US/JP/UK before their daily-yield start).* Fetch OECD MEI
     monthly 10-year yields (`IRLTLT01`), reprice a constant-maturity 10y par bond
     month-to-month with coupon carry (`monthly_bond_returns`), and smooth each month's
     return evenly across that month's trading days. Where a country has no observed yield in
     a month, the GDP-weighted basket monthly bond return is used so that country still
     contributes its genuine daily FX with a basket-average rate move.
4. **Combine and weight.** Per country and day, `country_return = (1 + bond) *
   (1 + daily_fx) - 1` (where `bond` is the daily override if present, else the
   within-month-smoothed monthly value); the basket daily return is the GDP-weighted sum
   across countries.
5. **Annual overlay.** For each calendar year, multiply every day's `(1 + return)` by a
   constant factor so the year compounds exactly to the JST annual basket return. The first
   trading day carries no return.
6. **Observed segment.** From the BND/BWX overlap onward, use a 45%/55% daily-rebalanced
   adjusted-close return blend, compounding the same level continuously.
7. Set `Close == Adj Close`; this is a single total-return proxy level.

Representative bond maturity is 10 years (US uses the in-repo ~8.5y 7-10y Treasury TR — a
minor maturity difference absorbed by the annual overlay). The rate leg is genuinely daily
for US (1970+), UK (1979+) and Japan (1986-07+) — together ≈62% of the basket from 1979.
The remaining countries use OECD MEI monthly yields, and countries without an early yield
(e.g. Italy before 1991, Spain 1980, Nordics 1980s) are basket-proxied on the rate leg
until their data begins, but contribute genuine daily FX throughout.

## Update Method

`src/update_global_bonds.py` rebuilds the full public-source chain (it calls the build
`main()`). Ordinary daily updates reuse cached historical JST/BIS/OECD/MoF/BoE raw files
from `sources/raw/` and refresh only the live BND/BWX Yahoo tail. Use
`--refresh-static-sources` only when intentionally refetching the heavy historical inputs.
Refresh the in-repo `ITT` dataset first, since the U.S. daily rate leg reads
`intermediate_term_us_treasury.csv`.

## Tests

Validation checks schema, 1970 coverage, sorted unique dates, positive levels, return
arithmetic, the per-year JST anchor invariant for 1970-2006, and exact daily return
matches to the BND/BWX adjusted-close blend for the observed segment. Regression tests
guard the build: the early segment must have many distinct daily returns per year (not the
old single constant value); its annualized volatility must fall in a realistic 3%-20% band;
two unambiguous USD shocks must move the basket in the correct direction (Plaza Accord
1985-09-23 up; Carter dollar-rescue 1978-11-02 down — also guards FX orientation); basket
weights must be economically sane (US largest, G4 > 50% — guards the real-GDP weighting);
and the daily rate leg must cover US (from 1970), Japan (from 1986) and UK (from 1979).

## Caveats

- The 1970-2007 segment is model-derived. The annual *level* is anchored to JST; the daily
  *path* is reconstructed from observed daily FX and observed bond returns. The rate leg is
  daily for US/UK/Japan (≈62% of the basket from 1979) but monthly for the rest, so genuine
  daily interest-rate moves before 2007 are only partially captured outside those markets.
- The early segment is government-bond-only and advanced-economy-only (16 countries). It is
  not a full global aggregate including corporate, securitized, emerging-market, or
  inflation-linked bonds.
- Currency exposure is intentionally unhedged. FX is now daily (BIS) in the path and annual
  (JST `xrusd`) in the anchor.
- Country weights use prior-year comparable real GDP (`rgdpmad` x `pop`), not market value
  of investable bond debt. (JST's nominal `gdp` column is not used for weights: its units
  are inconsistent across countries, so `gdp / xrusd` mis-weights the basket toward small
  economies.)
- Rate-leg coverage is staged: US daily from 1970, UK from 1979, Japan from 1986-07; before
  those dates and for all other countries the rate leg is monthly (and Italy/Spain/Nordics
  are basket-proxied until their OECD yield history begins). All countries carry daily FX
  throughout. So 1970-1979 has only the US on a daily rate leg, rising to ≈62% of the basket
  by 1986.
- US uses the in-repo ~8.5y 7-10y Treasury TR as its daily bond leg (vs a 10y par model for
  UK/Japan); this small maturity difference is immaterial and absorbed by the annual overlay.
- The 2007 splice changes methodology to an observed 45% BND / 55% BWX daily-rebalanced
  blend, which is not an official global aggregate index.
- JST has non-commercial license terms; review before redistribution outside this project.
- Preferred upgrades are licensed unhedged Bloomberg Global Aggregate / FTSE WGBI daily
  history, or daily per-country sovereign yield history for the remaining markets (Germany,
  Canada, France, Italy, …) back to the 1970s, which would extend the daily rate leg beyond
  the current US/UK/Japan ≈62%. Germany was investigated: free daily yields reach only 1997.
