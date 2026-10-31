# 2x Daily-Reset U.S. Large Cap, SSO-like Source Notes

Accessed: 2026-10-31

## USLCAP base dataset (us_large_cap_sp500)

- Path: `data/processed/us_large_cap_sp500.csv`
- Use: underlying daily total return (`u`) for the 2x daily-reset model.
- Finding: S&P 500 daily total return (French/CRSP large cap before ^SP500TR, then ^SP500TR).

## Yahoo Finance Chart API — ^IRX (financing benchmark)

- Endpoint: https://query1.finance.yahoo.com/v8/finance/chart/%5EIRX
- Use: financing-rate benchmark for the borrowed (1x) exposure, plus spread 0.0080.

## Yahoo Finance Chart API — SSO (observed ETF + calibration target)

- Endpoint: https://query1.finance.yahoo.com/v8/finance/chart/SSO
- Use: observed adjusted-close total returns from the trading day after 2006-06-21.
- Finding: Over 5119 SSO trading days from 2006-06-21: daily correlation 0.9954, annualized tracking error 3.8%, cumulative model/SSO ratio 0.9990.

## Fund parameters

- Source: https://www.proshares.com/our-etfs/leveraged-and-inverse/sso
- Objective: S&P 500.
- Expense ratio: net 0.84%, gross 0.88%.
- Inception: 2006-06-19.
- Caveat: Calibrated to SSO cumulative growth over the 2006+ overlap. The SSO fee waiver runs to 2027-09-30.
