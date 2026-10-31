# 2x Daily-Reset Global Stocks, WLDU-like Source Notes

Accessed: 2026-10-31

## GLSTOCK base dataset (global_stocks)

- Path: `data/processed/global_stocks.csv`
- Use: underlying daily total return (`u`) for the 2x daily-reset model.
- Finding: GLSTOCK global all-world equity total return; VT adjusted-close returns from 2008-06-27.

## Yahoo Finance Chart API — ^IRX (financing benchmark)

- Endpoint: https://query1.finance.yahoo.com/v8/finance/chart/%5EIRX
- Use: financing-rate benchmark for the borrowed (1x) exposure, plus spread 0.0080.

## Yahoo Finance Chart API — WLDU (observed ETF + calibration target)

- Endpoint: https://query1.finance.yahoo.com/v8/finance/chart/WLDU
- Use: observed adjusted-close total returns from the trading day after 2026-03-10.
- Finding: Over 160 WLDU trading days from 2026-03-10: daily correlation 0.9938, annualized tracking error 3.3%, cumulative model/WLDU ratio 1.0407.

## Fund parameters

- Source: https://leverageshares.com/us/etfs/leverage-shares-2x-long-world-stock-daily-etf/
- Objective: 2x VT (Vanguard Total World Stock ETF), through total return swaps.
- Expense ratio: net 0.75%, gross not separately disclosed.
- Inception: 2026-03-10.
- Caveat: WLDU's ~160-day overlap cannot calibrate a spread: the bisection hit its 3% bound, with the SSO-spread model running ~4% above WLDU over 2026-03 to 2026-10 at 0.994 daily correlation. The SSO spread (same leverage, swap-financed equity) is used instead and should be revisited once WLDU has several years of history.
