# GLSTBOND - Unhedged Global Short-Term (1-3yr) Government Bonds

Dataset identifier: `global_short_term_bonds`

Backtest alias: `GLSTBOND`

Status: complete model-derived public-source proxy

## Asset Definition

`GLSTBOND` is an unhedged global short-term (1-3yr) government-bond total-return proxy in USD.
It is ISHG-like in maturity (developed 1-3yr sovereigns) but global in scope - it **includes
the US**, unlike ISHG's ex-US index. It is the short-duration sibling of `GLBOND`.

- `Close` / `Price Return`: **gross-of-fee** total-return level and return.
- `Adj Close` / `Total Return`: **net-of-fee** total-return level and return (a representative
  ~0.26%/yr fund expense drag). This is the investable series the backtester reads.

Currency exposure is intentionally unhedged.

## Output Files

| File | Path |
|---|---|
| CSV | `data/processed/global_short_term_bonds.csv` |
| Parquet | `data/processed/global_short_term_bonds.parquet` |
| Manifest | `sources/manifests/global_short_term_bonds.yml` |
| Citation notes | `sources/citations/global_short_term_bonds.md` |
| Build script | `src/build_global_short_term_bonds.py` |
| Update script | `src/update_global_short_term_bonds.py` |
| Test file | `tests/validation/test_global_short_term_bonds_contract.py` |

Coverage starts on `1970-01-02`.

## Source Chain

| Segment | Dates | Source | Quality flag |
|---|---|---|---|
| Direct daily reconstruction | 1970-01-02 to 2009-01-29 | BIS daily FX + daily 2yr US/JP/UK + OECD MEI monthly 2yr-interpolated yields elsewhere; GDP-weighted; net of fee | `model_direct_daily_fx_2y_yield_global_short_govt_bond_unhedged_net_of_fee` |
| Observed GDP-weighted blend | 2009-01-30 onward | `w_us`*SHY + `(1-w_us)`*mean(ISHG, BWZ), annually rebalanced | `observed_shy_ishg_bwz_gdp_weighted_short_govt_bond_unhedged_net_of_fee` |

Daily 2yr bond-return sources for the three largest weights:

| Country | Daily 2yr source | Daily from |
|---|---|---|
| US | in-repo 2yr Treasury total return (`short_term_us_treasury.csv`) | 1970-01 |
| Japan | MoF daily 2yr JGB yield (`jgbcm_all.csv`, 2yr column) | 1974-09 |
| UK | BoE GLC daily 2yr nominal spot yield | 1979-01 |

All other countries, and earlier years, use the OECD MEI monthly 2yr-interpolated rate leg
(JST annual `stir`/`ltrate` as the pre-OECD fallback).

## Build Method

Unlike `GLBOND`, **there is no JST annual overlay**. JST's `bond_tr` is a ~10yr long-bond
return - the wrong annual *level* for a 1-3yr series - and short bonds are carry-dominated, so
the series is built **directly** from observed daily/monthly short-end data.

1. **Weights (JST).** Prior-year comparable real GDP (`rgdpmad` x `pop`) gives the per-year
   basket weights (`jst_basket`) and the US-vs-ex-US split for the observed blend
   (`us_weight_by_year`, carried forward past JST's last year).
2. **2yr yield per country (monthly).** A 2-year yield is interpolated linearly in maturity
   between the OECD MEI 3-month (`IR3TIB01`, ~0.25y) and 10-year (`IRLTLT01`, ~10y) rates. For
   months before a country's OECD coverage, the JST annual `stir`/`ltrate` (percent),
   interpolated to 2yr and held across the year, fills the gap so every country has a 2yr
   yield back to 1970 (`build_two_year_yields`).
3. **Daily FX leg (BIS).** Genuine daily USD FX returns per country (US leg = 1.0), identical
   to GLBOND.
4. **Rate leg.** Daily for US (in-repo 2yr Treasury TR, 1970+), Japan (MoF 2yr JGB, 1974-09+)
   and UK (BoE 2yr spot, 1979+) via a 2yr par-bond reprice + carry; monthly elsewhere
   (constant-maturity 2yr par bond repriced month-to-month, smoothed within month). Countries
   without a yield in a month fall back to the GDP-weighted basket monthly bond return.
5. **Combine.** Per country and day, `country_return = (1 + bond) * (1 + daily_fx) - 1`; the
   gross basket daily return is the GDP-weighted sum. Compounded directly (no rescaling).
6. **Fees.** The net leg (`Adj Close`/`Total Return`) subtracts a representative ~0.26%/yr
   expense drag (actual/365) in the model era. In the observed era the ETF returns are already
   net, so the gross leg (`Close`/`Price Return`) adds the fee back.
7. **Observed segment.** From 2009-01-30, daily return = `w_us`*SHY + `(1-w_us)`*mean(ISHG,
   BWZ) from adjusted-close returns, annually rebalanced by GDP.

Representative bond maturity is 2 years (mid-point of the 1-3yr band). The daily rate leg
covers the US (1970+), Japan (1974-09+) and UK (1979+) - Japan's short-end leg starts twelve
years earlier than GLBOND's 10yr because the MoF file publishes the 1-9yr nodes from 1974.

## Update Method

`src/update_global_short_term_bonds.py` rebuilds the full public-source chain (it calls the
build `main()`), mirroring GLBOND. Ordinary daily updates reuse cached historical
JST/BIS/OECD/MoF/BoE raw files from `sources/raw/` and refresh only the live SHY/ISHG/BWZ
Yahoo tail. Use `--refresh-static-sources` only when intentionally refetching the heavy
historical inputs. Refresh the in-repo `STT` dataset first, since the US daily leg reads
`short_term_us_treasury.csv`.

## Tests

`tests/validation/test_global_short_term_bonds_contract.py` checks schema, 1970 coverage,
sorted unique dates, positive levels, and that **both** `Close`/`Price Return` (gross) and
`Adj Close`/`Total Return` (net) recompute. It verifies the net-of-fee drag matches the
modeled rate (~0.26%/yr) and that `Adj Close <= Close` throughout; that the observed segment
reproduces the GDP-weighted SHY + ISHG/BWZ net blend exactly (tol 1e-10, >4000 rows); that
the early segment is genuinely daily (>100 distinct returns/year), has realistic unhedged vol
(3%-12%), and moves correctly on the Plaza Accord (1985-09-23 up) and Carter dollar-rescue
(1978-11-02 down) shocks; that basket weights are economically sane (US largest, G4 > 50%);
and that the daily 2yr rate leg covers US (1970), Japan (1974-09) and UK (1979).

## Caveats

- The 1970-2009 segment is model-derived. It is built directly from observed daily FX (all 16
  countries) and a 2yr par bond; the rate leg is genuinely daily only for US/JP/UK and monthly
  (OECD-interpolated, JST-backstopped) for the rest, so daily rate moves before 2009 are only
  partially captured outside those markets.
- The early segment is government-bond-only and advanced-economy-only (16 countries). It is
  not a full global short aggregate (no corporate, securitized, EM or inflation-linked bonds).
- The 2yr yield is interpolated from the 3-month and 10-year rates where a true 2yr is
  unavailable; this approximates the short-end curve shape but is not an observed 2yr fixing.
- Currency exposure is intentionally unhedged - FX dominates the daily volatility (~5%).
- Country weights use prior-year comparable real GDP, not market value of investable short
  sovereign debt. Market-cap (e.g. BIS debt-securities) weighting is a documented future
  upgrade.
- The observed segment is a GDP-weighted SHY + ISHG/BWZ blend, not an official global short
  government-bond index; the US-vs-ex-US split is carried forward at JST's last GDP year.
- Modeled fees are a single representative ~0.26%/yr drag, not each fund's exact, time-varying
  expense ratio.
- JST has non-commercial license terms; review before redistribution outside this project.
- Preferred upgrade: a licensed unhedged FTSE WGBI Developed 1-3yr / Bloomberg Short Global
  Treasury daily history, or daily per-country 2yr sovereign yields for the remaining markets
  (Germany free daily yields reach only ~1997) to extend the daily rate leg beyond US/JP/UK.
