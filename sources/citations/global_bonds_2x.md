# 2x Daily-Reset Global Bonds, modeled with UST-style fees Source Notes

Accessed: 2026-10-31

## GLBOND base dataset (global_bonds)

- Path: `data/processed/global_bonds.csv`
- Use: underlying daily total return (`u`) for the 2x daily-reset model.
- Finding: GLBOND unhedged global bond total return; 45% BND + 55% BWX from 2007-10-12.

## Yahoo Finance Chart API — ^IRX (financing benchmark)

- Endpoint: https://query1.finance.yahoo.com/v8/finance/chart/%5EIRX
- Use: financing-rate benchmark for the borrowed (1x) exposure, plus spread -0.0033.

## Fund parameters

- Source: https://www.proshares.com/our-etfs/leveraged-and-inverse/ust
- Objective: none: no 2x global bond fund exists.
- Expense ratio: net 0.95% (UST), gross 1.24% (UST).
- A search for a 2x fund on this exposure (ProShares fund list, US issuers, UCITS listings) found none on 2026-10-31.
- Caveat: No fund to calibrate against. Uses the UST spread, which is negative partly because the ITT base already deducts IEF's fee. GLBOND's base deducts BND/BWX fees (blended ~0.21%), so the same spread does not offset it exactly.
