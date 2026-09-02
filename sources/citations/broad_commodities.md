# Broad Commodities Source Notes

Accessed: 2026-06-17 (Yahoo segments), 2026-06-26 (S&P GSCI Total Return anchor)

## S&P GSCI Total Return anchor - MacroMicro (Segments 0-1, 1970-1991)

- URL: https://en.macromicro.me/series/2692/sp-gsci-index ("S&P GSCI - Total Return Index")
- Local source-cache file: `sources/raw/broad_commodities_gsci_tr_macromicro.csv` (Date, GSCI_TR_Index); the raw cache is not part of the public release by default.
- Use: anchor for the 1970-1991 reconstruction. Adj Close (total return) tracks this series; Close (excess return) strips the daily `^IRX` collateral.
- Access method: free programmatic S&P GSCI Total Return is paywalled everywhere (Yahoo `^SPGSCITR` empty; `GSG` ETF 2006+; FRED/DBnomics none; Investing.com and Barchart blocked). MacroMicro's free series page renders the data in a Highcharts object; extracted in-browser (Claude-in-Chrome) from `window.Highcharts.charts[...].series[0]` and saved as a static CSV.
- Finding: full 1970-01-02 -> 2026-06-25 range, base 100 at 1970-01-02, **downsampled to 358 points (~57-day/bi-monthly spacing)**. The series is a genuine roll-inclusive, collateralized total return (validation below). It is historical and does not change, so it is retained in the local source cache; the raw file is excluded from the public release by default and only the DBC tail refreshes on update.
- Validation: over 1984-1991 the GSCI TR grew 3.08x vs Yahoo `^SPGSCI` spot 1.04x; collateral (~7.3%/yr) explains ~1.64x and the residual ~1.8x/7yr implies ~9%/yr roll yield (energy-heavy backwardation). Over 1991-2006 the GSCI TR grew 3.06x vs `^BCOM` excess return 1.83x (~1.67x = collateral + GSCI energy tilt). Confirms total-return (spot + roll + collateral) behavior.
- Caveats: (1) downsampled republication, not a licensed daily S&P feed - Segment 0 daily volatility is smoothed and Segment 1's daily shape comes from `^SPGSCI` spot; (2) S&P GSCI is back-tested before its 1991 launch; (3) GSCI is more energy-heavy than DBC; (4) S&P-derived data via a third-party republication - review licensing before redistributing derived data.

## Yahoo Finance Chart API - ^SPGSCI (Segment 1 daily shape)

- URL: https://query1.finance.yahoo.com/v8/finance/chart/%5ESPGSCI
- Use: Segment 1 (`1984-01-04` to `1991-01-02`) daily spot **shape** only. Daily `^SPGSCI` returns are rescaled per anchor interval so each interval compounds to the GSCI TR; this restores genuine daily volatility (~16%/yr) and event timing while the level carries the anchor's roll + collateral.
- Finding: available daily from `1984-01-03`; adjusted close equals close (spot index, no distributions).
- Caveat: spot only - it supplies the shape, not the level. Pre-1991 GSCI is retrospective back-history.

## Yahoo Finance Chart API - ^BCOM (Segment 2)

- URL: https://query1.finance.yahoo.com/v8/finance/chart/%5EBCOM
- Use: Segment 2 (`1991-01-03` to `2006-02-06`) excess return; Adj Close adds `^IRX` collateral.
- Finding: available daily from `1991-01-02`; adjusted close equals close. 2021 annual return matched BCOM excess-return behavior, so Yahoo `^BCOM` is treated as excess return.
- Caveat: different weights/roll from GSCI and DBC; index-type validation is indirect (no official Bloomberg metadata in the payload).

## Yahoo Finance Chart API - DBC (Segment 3)

- URL: https://query1.finance.yahoo.com/v8/finance/chart/DBC
- Use: Segment 3 (`2006-02-07` to present) observed ETF total return (Yahoo adjusted close).
- Finding: available daily from `2006-02-06`; adjusted close differs from close.
- Caveat: ETF net return (~0.89%/yr expenses), optimum-yield roll, Yahoo-adjusted-close dependency; not a gross index total return.

## Yahoo Finance Chart API - ^IRX (collateral, Segments 0-2)

- URL: https://query1.finance.yahoo.com/v8/finance/chart/%5EIRX
- Use: 13-week T-bill annualized rate for the collateral model and the Segment 0 trading calendar.
- Finding: daily from `1970-01-02`; close is the rate in percent; daily accrual `IRX/100/365`.
- Caveat: missing dates forward-filled. FRED DTB3/TB3MS is an equivalent public source but FRED CSV access was unreliable in prior sessions.

## Superseded / not used

- **World Bank Commodity Markets Pink Sheet (former Segment 0)**: the monthly `Total Index` spot model (`broad_commodities_world_bank_cmo_monthly.xlsx`) was used for 1970-1983 until 2026-06-26. Replaced by the GSCI Total Return anchor because it was spot-only (no roll yield) and its 67%-energy Laspeyres export-value weights differ materially from DBC/GSCI. Removed from the active build path.
- **Previous LBMA Gold PM + Silver fill**: removed earlier - not broad commodities. Gold remains its own `GOLDPM` dataset.
- **AQR "Commodities for the Long Run"** (monthly, roll-inclusive, 1877+): freely downloadable but equal-weighted, so not chosen as the energy-tilted DBC-like anchor.
- **Yahoo `^SPGSCITR` / `^BCOMTR`, GSG, DJP**: no usable long history / start later than DBC.

## 1970-1983 daily broad-commodity source search (still relevant)

No free **daily** broad-commodity history exists before 1984: Stooq CRB/CCI returned a JS verification page; CRBTrader required authentication; Nasdaq Data Link CHRIS was Incapsula-blocked; Yahoo broad index symbols (`^CRB`, `^TRJEFFCRB`, etc.) and continuous futures (`GC=F`, `CL=F`, grains, softs) start ~2000; EIA WTI starts 1986; BLS/NBER/AQR/IMF/World Bank are monthly. Roll yield requires futures-curve data, unavailable for free pre-1990. This is why Segment 0 (1970-1983) is the GSCI TR anchor log-linearly smoothed to daily rather than a genuine daily reconstruction.

## Current data gaps to preserve in handover

- **Segments 0-1 anchored to a downsampled GSCI TR republication**: level tracks the index to within a few percent; Segment 0 daily volatility is smoothed; Segment 1's daily shape is `^SPGSCI` spot.
- **GSCI is energy-heavier than DBC** and back-tested before 1991.
- **BCOM validation gap**: Segment 2 treats `^BCOM` as excess return by behavior, not licensed metadata.
- **DBC ETF gap**: Segment 3 is ETF net adjusted close, not gross benchmark total return.
- **Splice gaps**: 1991 and 2006 are methodology changes across source families (numerical continuity, not economic).
- **OHLCV gap**: model/index segments have blank `Open`, `High`, `Low`, `Volume`.
