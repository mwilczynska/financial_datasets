# 2x Daily-Reset Long-Term Treasury, UBT-like Source Notes

Accessed: 2026-10-31

## LTT base dataset (long_term_us_treasury)

- Path: `data/processed/long_term_us_treasury.csv`
- Use: underlying daily total return (`u`) for the 2x daily-reset model.
- Finding: LTT TLT-like long Treasury total return (Fed 25-year par model, VUSTX, then TLT).

## Yahoo Finance Chart API — ^IRX (financing benchmark)

- Endpoint: https://query1.finance.yahoo.com/v8/finance/chart/%5EIRX
- Use: financing-rate benchmark for the borrowed (1x) exposure, plus spread -0.0035.

## Yahoo Finance Chart API — UBT (observed ETF + calibration target)

- Endpoint: https://query1.finance.yahoo.com/v8/finance/chart/UBT
- Use: observed adjusted-close total returns from the trading day after 2010-01-21.
- Finding: Over 4217 UBT trading days from 2010-01-21: daily correlation 0.9848, annualized tracking error 5.2%, cumulative model/UBT ratio 1.0005.

## Fund parameters

- Source: https://www.proshares.com/our-etfs/leveraged-and-inverse/ubt
- Objective: ICE U.S. Treasury 20+ Year Bond Index.
- Expense ratio: net 0.95%, gross 0.98%.
- Inception: 2010-01-19.
- Caveat: Calibrated to UBT cumulative growth over the 2010+ overlap. Negative for the same reason as ITT2X: the base is net of TLT's 0.15% fee.
