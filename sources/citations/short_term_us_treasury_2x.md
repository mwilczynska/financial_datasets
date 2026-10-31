# 2x Daily-Reset Short-Term Treasury, modeled with UST-style fees Source Notes

Accessed: 2026-10-31

## STT base dataset (short_term_us_treasury)

- Path: `data/processed/short_term_us_treasury.csv`
- Use: underlying daily total return (`u`) for the 2x daily-reset model.
- Finding: STT SHY-like short Treasury total return (Fed curve model, VFISX, then SHY).

## Yahoo Finance Chart API — ^IRX (financing benchmark)

- Endpoint: https://query1.finance.yahoo.com/v8/finance/chart/%5EIRX
- Use: financing-rate benchmark for the borrowed (1x) exposure, plus spread -0.0033.

## Fund parameters

- Source: https://www.proshares.com/our-etfs/leveraged-and-inverse/ust
- Objective: none: no 2x 1-3 year Treasury fund exists.
- Expense ratio: net 0.95% (UST), gross 1.24% (UST).
- A search for a 2x fund on this exposure (ProShares fund list, US issuers, UCITS listings) found none on 2026-10-31.
- Caveat: No fund to calibrate against. Uses the UST spread. STT's base deducts SHY's 0.15% fee from 2002, close to IEF's, so the offset is similar.
