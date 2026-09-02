# 3x Long-Term Treasury (TMF-like) Source Notes

Accessed: 2026-06-17

## LTT base dataset (long_term_us_treasury)

- Path: `data/processed/long_term_us_treasury.csv`
- Use: underlying daily total return (`u`) for the 3x daily-reset model.
- Finding: the `Total Return` column is a TLT-like long-term (20+ year) U.S. Treasury daily
  total return — Federal Reserve nominal yield-curve 25-year par model before VUSTX, then VUSTX
  adjusted returns, then TLT adjusted returns — covering 1970-01-02 to present.
- Caveat: the pre-2002 underlying is model-/fund-derived (Fed 25-year constant-maturity par
  model and VUSTX), not the ICE 20+ Year index that TMF actually tracks, so the synthetic 3x
  series inherits a duration/exposure mismatch before TLT history begins (see methodology).

## Yahoo Finance Chart API — ^IRX (financing benchmark)

- Endpoint: https://query1.finance.yahoo.com/v8/finance/chart/%5EIRX
- Use: financing-rate benchmark for the borrowed (2x) exposure.
- Finding: Yahoo returns the 13-week T-bill annualized discount yield (percent) daily from
  1970-01-02.
- Caveat: `^IRX` is a T-bill proxy for the fund's swap/futures financing rate. A borrowing
  spread is added on top and calibrated to the TMF overlap; the true financing rate (closer to
  the overnight rate plus a counterparty spread) is not directly observed.

## Yahoo Finance Chart API — TMF (observed ETF + calibration target)

- Endpoint: https://query1.finance.yahoo.com/v8/finance/chart/TMF
- Use: observed adjusted-close total returns from inception onward, and the calibration target
  for the synthetic pre-inception model.
- Finding: Yahoo returns TMF daily adjusted history from 2009-04-16 (Direxion Daily 20+ Year
  Treasury Bull 3X Shares inception). Over the 2009-2026 overlap the calibrated synthetic model
  reproduces TMF with a daily-return correlation of 0.997, an annualized tracking error of
  ~3.7%, and cumulative growth within ~0.04% of actual TMF. Note that TMF's cumulative total
  return over this rising-rate period is well below 1.0 (large volatility decay).
- Caveat: Yahoo/yfinance data rights and terms must be reviewed before redistribution. TMF
  adjusted close is the production source; official Direxion NAV total-return history was not
  used.

## Direxion TMF prospectus / fund page

- URL: https://www.direxion.com/product/daily-20-year-treasury-bull-bear-3x-etfs
- Use: parameter reference.
- Finding: TMF seeks daily investment results, before fees and expenses, of 300% of the daily
  performance of the ICE U.S. Treasury 20+ Year Bond Index (the same index family TLT tracks);
  the fund's total annual operating expense ratio is about 1.06%.
- Caveat: TMF gains 3x exposure via swaps and Treasury futures, whose financing and roll
  behavior the `^IRX`+spread model only approximates. Daily reset and financing on the borrowed
  exposure are inherent to the daily-objective structure rather than separately observed.
