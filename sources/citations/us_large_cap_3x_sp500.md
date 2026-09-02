# 3x U.S. Large-Cap (UPRO-like) Source Notes

Accessed: 2026-06-17

## USLCAP base dataset (us_large_cap_sp500)

- Path: `data/processed/us_large_cap_sp500.csv`
- Use: underlying daily total return (`u`) for the 3x daily-reset model.
- Finding: the `Total Return` column is the S&P 500 daily total return (Kenneth French/CRSP
  large-cap proxy before `^SP500TR`, then `^SP500TR`), covering 1970-01-02 to present.
- Caveat: the pre-1988 underlying is a CRSP large-cap total-return proxy, so the synthetic 3x
  series inherits that approximation in addition to its own modeling assumptions.

## Yahoo Finance Chart API — ^IRX (financing benchmark)

- Endpoint: https://query1.finance.yahoo.com/v8/finance/chart/%5EIRX
- Use: financing-rate benchmark for the borrowed (2x) exposure.
- Finding: Yahoo returns the 13-week T-bill annualized discount yield (percent) daily from
  1970-01-02, the same source the broad-commodities dataset uses for T-bill collateral.
- Caveat: `^IRX` is a T-bill proxy for the fund's swap/borrowing rate. A borrowing spread is
  added on top and calibrated to the UPRO overlap; the true swap financing rate (closer to the
  overnight/federal-funds rate plus a counterparty spread) is not directly observed here.

## Yahoo Finance Chart API — UPRO (observed ETF + calibration target)

- Endpoint: https://query1.finance.yahoo.com/v8/finance/chart/UPRO
- Use: observed adjusted-close total returns from inception onward, and the calibration target
  for the synthetic pre-inception model.
- Finding: Yahoo returns UPRO daily adjusted history from 2009-06-25 (ProShares UltraPro S&P500
  inception). Over the 2009-2026 overlap the calibrated synthetic model reproduces UPRO with a
  daily-return correlation of 0.998, an annualized tracking error of ~3.2%, and cumulative
  growth within ~0.01% of actual UPRO.
- Caveat: Yahoo/yfinance data rights and terms must be reviewed before redistribution. UPRO
  adjusted close is the production source; official ProShares NAV total-return history was not
  used.

## ProShares UPRO prospectus / fund page

- URL: https://www.proshares.com/our-etfs/leveraged-and-inverse/upro
- Use: parameter reference.
- Finding: UPRO seeks daily investment results, before fees and expenses, of 300% of the daily
  performance of the S&P 500; the fund's annual expense ratio is 0.91%.
- Caveat: the fund references the S&P 500; the model uses S&P 500 **total** return (USLCAP) as the
  underlying because UPRO's swap exposure and NAV reflect index dividends. Daily reset and
  financing on the borrowed exposure are inherent to the daily-objective structure rather than
  separately observed.
