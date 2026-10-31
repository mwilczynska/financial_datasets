# 2x Daily-Reset Intermediate-Term Treasury, UST-like Source Notes

Accessed: 2026-10-31

## ITT base dataset (intermediate_term_us_treasury)

- Path: `data/processed/intermediate_term_us_treasury.csv`
- Use: underlying daily total return (`u`) for the 2x daily-reset model.
- Finding: ITT IEF-like intermediate Treasury total return (Fed 8.5-year par model, VFITX, then IEF).

## Yahoo Finance Chart API — ^IRX (financing benchmark)

- Endpoint: https://query1.finance.yahoo.com/v8/finance/chart/%5EIRX
- Use: financing-rate benchmark for the borrowed (1x) exposure, plus spread -0.0033.

## Yahoo Finance Chart API — UST (observed ETF + calibration target)

- Endpoint: https://query1.finance.yahoo.com/v8/finance/chart/UST
- Use: observed adjusted-close total returns from the trading day after 2010-02-02.
- Finding: Over 4209 UST trading days from 2010-02-02: daily correlation 0.9724, annualized tracking error 3.1%, cumulative model/UST ratio 0.9994.

## Fund parameters

- Source: https://www.proshares.com/our-etfs/leveraged-and-inverse/ust
- Objective: ICE U.S. Treasury 7-10 Year Bond Index.
- Expense ratio: net 0.95%, gross 1.24%.
- Inception: 2010-01-19.
- Caveat: Calibrated to UST cumulative growth over the 2010+ overlap. The spread is negative mainly because the ITT base is net of IEF's 0.15% fee, which 2x leverage doubles; UST tracks the gross index. UST is thinly traded, which lowers its daily correlation (0.97).
