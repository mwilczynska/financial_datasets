# 3x Intermediate-Term Treasury (TYD-like) Source Notes

Accessed: 2026-06-17

## Naming / leverage clarification

The project backlog originally listed "UST" as the 3x intermediate-Treasury ETF. This is
incorrect: **UST** (ProShares Ultra 7-10 Year Treasury) is a **2x** fund. The genuine **3x**
7-10 year Treasury ETF is **TYD** (Direxion Daily 7-10 Year Treasury Bull 3X Shares), which is
therefore the calibration and validation target for this 3x dataset. UST is the future target
for a separate `ITT2X` (2x) dataset.

## ITT base dataset (intermediate_term_us_treasury)

- Path: `data/processed/intermediate_term_us_treasury.csv`
- Use: underlying daily total return (`u`) for the 3x daily-reset model.
- Finding: the `Total Return` column is an IEF-like intermediate-term (7-10 year) U.S. Treasury
  daily total return — Federal Reserve nominal yield-curve 8.5-year par model before VFITX, then
  VFITX adjusted returns, then IEF adjusted returns — covering 1970-01-02 to present.
- Caveat: the pre-2002 underlying is model-/fund-derived (Fed 8.5-year constant-maturity par
  model and VFITX), not the ICE 7-10 Year index that TYD tracks; the synthetic 3x series inherits
  that exposure approximation.

## Yahoo Finance Chart API — ^IRX (financing benchmark)

- Endpoint: https://query1.finance.yahoo.com/v8/finance/chart/%5EIRX
- Use: financing-rate benchmark for the borrowed (2x) exposure.
- Finding: Yahoo returns the 13-week T-bill annualized discount yield (percent) daily from
  1970-01-02.
- Caveat: `^IRX` is a T-bill proxy for the fund's swap/futures financing rate. A borrowing
  spread is added and calibrated to the TYD overlap.

## Yahoo Finance Chart API — TYD (observed ETF + calibration target)

- Endpoint: https://query1.finance.yahoo.com/v8/finance/chart/TYD
- Use: observed adjusted-close total returns from inception onward, and the calibration target
  for the synthetic pre-inception model.
- Finding: Yahoo returns TYD daily adjusted history from 2009-04-16 (Direxion Daily 7-10 Year
  Treasury Bull 3X Shares inception). Over the full overlap the calibrated model matches TYD's
  cumulative growth within ~0.02%, but the **full-overlap daily-return correlation is only ~0.88
  with ~10% annualized tracking error**. A year-by-year breakdown shows correlation of 0.92-0.99
  in 2009-2013 and 0.94-0.996 in 2019-2026, but it collapses to 0.37-0.66 in 2014-2018 with many
  >2% daily gaps. This is the signature of TYD being a thinly-traded, low-AUM fund with stale /
  illiquid Yahoo closing prices mid-decade — a TYD market-data quality issue, not a model error.
- Caveat: Yahoo/yfinance data rights and terms must be reviewed before redistribution. The
  observed segment faithfully reproduces TYD's (noisy) adjusted-close returns; calibration uses
  cumulative growth (robust to mean-reverting stale-price noise) rather than daily tracking.

## Direxion TYD prospectus / fund page

- URL: https://www.direxion.com/product/daily-7-10-year-treasury-bull-bear-3x-etfs
- Use: parameter reference.
- Finding: TYD seeks daily investment results, before fees and expenses, of 300% of the daily
  performance of the ICE U.S. Treasury 7-10 Year Bond Index (the IEF benchmark); the fund's
  total annual operating expense ratio is about 1.09%.
- Caveat: TYD gains 3x exposure via swaps and Treasury futures, whose financing and roll behavior
  the `^IRX`+spread model only approximates. The low calibrated spread (0.19%) partly reflects
  fund fee waivers.

## ProShares UST (rejected — wrong leverage)

- URL: https://www.proshares.com/our-etfs/leveraged-and-inverse/ust
- Finding: UST is ProShares Ultra 7-10 Year Treasury, a **2x** fund (inception 2010-01), not 3x.
- Decision: not used for this 3x dataset; documented as the future validation target for a
  separate `ITT2X` (2x) dataset.
