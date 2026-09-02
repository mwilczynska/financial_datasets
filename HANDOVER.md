# Handover

This document is for handing the `financial_datasets` project between LLM agents. Treat it as a living operational note: update it whenever assumptions, dataset status, source decisions, or next tasks change.

## Repository

- Active repo path: `the repository root`
- GitHub remote: `https://github.com/mwilczynska/financial_datasets.git`
- Main branch: `main`
- Previous local checkouts and related external projects are not part of this repository.

## Project Goal

Build long-horizon daily asset-class datasets for portfolio backtesting. Outputs should be easy to slot into scripts that expect Yahoo Finance / `yfinance`-style data.

Required minimum target coverage is `1970-01-01` where a defensible daily source/method exists. Earlier data may be included if source quality and methodology support it.

Canonical output columns:

```text
Date, Open, High, Low, Close, Adj Close, Volume,
Price Return, Total Return, Source, Quality Flag, Source Notes
```

CSV and Parquet outputs are expected under `data/processed/`.

## Current Datasets

### USLCAP

- File: `data/processed/us_large_cap_sp500.csv`
- Alias in backtesting script: `USLCAP`
- Definition: U.S. large-cap equity / S&P 500-like series.
- `Close`: Yahoo `^GSPC` price index.
- `Adj Close`: daily total-return-adjusted level.
- Method: Kenneth French / CRSP `Hi 30` daily returns before Yahoo `^SP500TR`, then Yahoo `^SP500TR`.
- Status: complete.
- Caveat: pre-`^SP500TR` adjusted returns are a CRSP large-cap/blend proxy, not official S&P 500 total return.

### GOLDPM

- File: `data/processed/gold.csv`
- Alias in backtesting script: `GOLDPM` (the backtester reads `Adj Close`).
- Definition: GLD-tracking gold, including GLD's fee drag, extended to 1970 (redefined 2026-06-20).
- `Close` = LBMA Gold Price PM USD/oz (pure spot); `Price Return` = pure spot return.
- `Adj Close` = GLD-tracking total return: spot minus 0.40% GLD expense drag (actual/365) before GLD's 2004-11-18 inception, then observed GLD adjusted-close returns (Adj Close ∝ GLD). **`Adj Close != Close`** now (carries the fee). `Total Return` derives from `Adj Close`.
- **Calendar (important):** model era (1970→2004) on the LBMA (London) calendar; **observed era (2004→) on GLD's (NYSE) calendar** so the dataset aligns with GLD day-for-day. This matters because the backtester compares by intersecting daily-return dates and compounding — a London-calendar gold series vs a US-calendar ETF drifted **+47%/+1.96%/yr** over 2004-2026 on UK-bank-holiday days (fixed 2026-06-20). After the fix the script reproduces GLD with **0.000% gap**.
- Segments: `model_gld_tracking_lbma_pm_spot_minus_gld_expense` (1970→2004, LBMA cal), `observed_gld_etf_adjusted_total_return` (2004→, NYSE cal), `observed_gld_us_open_lbma_holiday_close_gld_step` (~141 UK-bank-holiday rows: no LBMA fix, Close stepped by GLD).
- Status: production built; observed era tracks GLD exactly (CAGR gap 0.0000%, ratio 1.0000).
- Caveat: pre-2004 is a fee-dragged model on the London calendar/PM fix (~10am ET), not the US 4pm close — daily timing differs but is cumulative-neutral. Use `Close`/`Price Return` for pure spot; the derived GOLD2X builds on `Price Return`. A US-close base (COMEX futures) is a deferred daily-fidelity upgrade (Stooq blocked, `GC=F` only to 2000).

### STT

- File: `data/processed/short_term_us_treasury.csv`
- Alias in backtesting script: `STT`
- Definition: SHY-like short-term nominal U.S. Treasury total-return series.
- Status: complete model-derived public-source dataset.
- Segments:
  - `1970-01-02` to `1991-10-28`: Federal Reserve nominal yield curve model, synthetic 2-year constant-maturity par Treasury; `Total Return` includes coupon carry. `Adj Close` compounds from 100 to ~1142 over this period due to high short rates.
  - VFISX segment: Yahoo adjusted returns used before SHY history is available.
  - SHY segment: Yahoo adjusted returns from SHY history onward.
- Caveat: pre-VFISX segment is model-derived, not observed fund/index history. A CRSP/WRDS issue-level Treasury build selecting 1-3 year bonds would be a future quality upgrade.

### ITT

- File: `data/processed/intermediate_term_us_treasury.csv`
- Alias in backtesting script: `ITT`
- Definition: IEF-like intermediate-term nominal U.S. Treasury total-return series.
- Status: complete model-derived public-source dataset.
- Segments:
  - `1970-01-02` to `1991-10-28`: Federal Reserve nominal yield curve model, synthetic 8.5-year constant-maturity par Treasury; `Total Return` includes coupon carry.
  - VFITX segment: Yahoo adjusted returns used before IEF history is available.
  - IEF segment: Yahoo adjusted returns from IEF history onward.
- Caveat: pre-VFITX segment is model-derived, not observed fund/index history. A CRSP/WRDS issue-level Treasury build selecting 7-10 year bonds would be a future quality upgrade.

### LTT

- File: `data/processed/long_term_us_treasury.csv`
- Alias in backtesting script: `LTT`
- Definition: TLT-like long-term nominal U.S. Treasury total-return series.
- Status: complete model-derived public-source dataset.
- Segments:
  - `1970-01-02` to `1986-05-19`: Synthetic 25-year constant-maturity par Treasury. Yield input hierarchy within segment: Fed `SVENY25`/`SVENY30` (Nov 1985 to VUSTX start) → Yahoo `^TYX` 30-year observed yield (1977-02-15 to Nov 1985) → Fed `SVENY10` proxy (Aug 1971 to Feb 1977; flat/inverted curve) → Svensson-fitted 10-year rate (1970 to Aug 1971). `Total Return` includes coupon carry.
  - VUSTX segment: Yahoo adjusted returns used before TLT history is available.
  - TLT segment: Yahoo adjusted returns from TLT history onward.
- Fixed bugs: (1) Raw Svensson BETA extrapolation at 25-year maturity is numerically unstable in the early 1970s (`SVENY25` is NaN before Nov 1985); direct use caused a spurious ~38% intra-year drawdown in 1970 — fixed by yield hierarchy above. (2) Previous-day bond price hardcoded as 100 was wrong in continuous compounding; fixed by computing previous price explicitly.
- Caveat: pre-VUSTX segment is model-derived, not observed fund/index history. The 1970-1977 sub-period uses a 10-year yield as a proxy for the 25-year yield (≤50 bps difference in the flat/inverted curve environment). A CRSP/WRDS issue-level Treasury build would be a future quality upgrade.

### USLCAP3X (derived leveraged)

- File: `data/processed/us_large_cap_3x_sp500.csv`
- Alias in backtesting script: `USLCAP3X` (not yet registered in `external backtesting application`)
- Definition: UPRO-like 3x daily-reset S&P 500 total return.
- `Close == Adj Close`: single 3x total-return NAV normalized to 100 on 1970-01-02. `Price Return == Total Return`. OHLCV blank.
- Status: complete model-derived (derived leveraged dataset).
- Segments:
  - `1970-01-02` to `2009-06-25` (UPRO inception day): synthetic 3x daily-reset model from `USLCAP` total return. `lev_ret = 3*u - 2*((^IRX/100 + 0.0065)*days/360) - 0.0091*days/365`. Flag `model_3x_daily_reset_synthetic_from_uslcap_total_return_minus_financing_and_fee`.
  - From `2009-06-26`: observed UPRO Yahoo adjusted-close daily total returns. Flag `observed_upro_etf_adjusted_total_return`.
- Calibration: borrowing spread 0.65% over `^IRX` calibrated to the UPRO overlap — daily corr 0.998, annualized tracking error ~3.2%, cumulative model/UPRO ratio ~1.0000.
- Build: 14,234 rows 1970-01-02 to 2026-06-15; synthetic 9,966, observed UPRO 4,268.
- Caveats: pre-2009 is model-derived, not observed UPRO history; constant-spread + `^IRX` financing proxy; inherits the pre-1988 CRSP large-cap proxy from `USLCAP`; path-dependent (not a simple 3x multiple of long-horizon returns).
- Build/update: `python src\build_us_large_cap_3x_sp500.py`; `python src\update_us_large_cap_3x_sp500.py` (refresh `USLCAP` first).

### LTT3X (derived leveraged)

- File: `data/processed/long_term_us_treasury_3x.csv`
- Alias in backtesting script: `LTT3X` (not yet registered in `external backtesting application`)
- Definition: TMF-like 3x daily-reset long-term (20+ yr) U.S. Treasury total return.
- `Close == Adj Close`: single 3x total-return NAV normalized to 100 on 1970-01-02. `Price Return == Total Return`. OHLCV blank.
- Status: complete model-derived (derived leveraged dataset).
- Segments:
  - `1970-01-02` to `2009-04-16` (TMF inception day): synthetic 3x daily-reset model from `LTT` total return. `lev_ret = 3*u - 2*((^IRX/100 + 0.0053)*days/360) - 0.0106*days/365`. Flag `model_3x_daily_reset_synthetic_from_ltt_total_return_minus_financing_and_fee`.
  - From `2009-04-17`: observed TMF Yahoo adjusted-close daily total returns. Flag `observed_tmf_etf_adjusted_total_return`.
- Calibration: borrowing spread 0.53% over `^IRX` calibrated to the TMF overlap — daily corr 0.997, annualized tracking error ~3.7%, cumulative model/TMF ratio ~1.0004.
- Build: 14,174 rows 1970-01-02 to 2026-06-15; synthetic 9,857, observed TMF 4,317.
- Caveats: pre-2009 is model-derived. **Key caveat — duration/exposure mismatch**: TMF tracks the ICE 20+ Year index, but the `LTT` underlying matches that only from 2002 (TLT); before 2002 it is a Fed 25-year par model + VUSTX. Path-dependent; TMF's cumulative return over the 2009-2026 rising-rate overlap is well below 1.0 (leverage decay).
- Build/update: `python src\build_long_term_treasury_3x.py`; `python src\update_long_term_treasury_3x.py` (refresh `LTT` first).

### ITT3X (derived leveraged)

- File: `data/processed/intermediate_term_us_treasury_3x.csv`
- Alias in backtesting script: `ITT3X` (registered by user in `external backtesting application`)
- Definition: TYD-like 3x daily-reset intermediate-term (7-10 yr) U.S. Treasury total return.
- **Naming**: the genuine 3x 7-10yr ETF is Direxion **TYD**. ProShares **UST** is a **2x** fund (the earlier "3x UST" backlog label was wrong); UST is the future target for a separate `ITT2X` (2x).
- `Close == Adj Close`: single 3x total-return NAV normalized to 100 on 1970-01-02. `Price Return == Total Return`. OHLCV blank.
- Status: complete model-derived (derived leveraged dataset).
- Segments:
  - `1970-01-02` to `2009-04-16` (TYD inception day): synthetic 3x daily-reset model from `ITT` total return. `lev_ret = 3*u - 2*((^IRX/100 + 0.0019)*days/360) - 0.0109*days/365`. Flag `model_3x_daily_reset_synthetic_from_itt_total_return_minus_financing_and_fee`.
  - From `2009-04-17`: observed TYD Yahoo adjusted-close daily total returns. Flag `observed_tyd_etf_adjusted_total_return`.
- Calibration: spread 0.19% over `^IRX` calibrated to TYD cumulative growth (ratio ~0.9998). Daily corr only ~0.88 full-overlap because TYD is thinly traded with stale Yahoo closes in 2014-2018; clean-era (2019+) corr > 0.95. Cumulative is robust to that mean-reverting noise, so it is the calibration target.
- Build: 14,158 rows 1970-01-02 to 2026-06-15; synthetic 9,841, observed TYD 4,317.
- Caveats: pre-2009 model-derived; observed segment inherits TYD's 2014-2018 stale-price noise; pre-2002 underlying is a Fed 8.5yr par model + VFITX, not the ICE 7-10yr index; path-dependent. Synthetic 2009 level ~5,000 (vs LTT3X ~650) shows lower leverage decay for lower-vol intermediate Treasuries.
- Build/update: `python src\build_intermediate_treasury_3x.py`; `python src\update_intermediate_treasury_3x.py` (refresh `ITT` first).

### GOLD2X (derived leveraged)

- File: `data/processed/gold_2x.csv`
- Alias in backtesting script: `GOLD2X` (not yet registered in `external backtesting application`)
- Definition: UGL-like 2x daily-reset gold total return.
- `Close == Adj Close`: single 2x total-return NAV normalized to 100 on 1970-01-02. `Price Return == Total Return`. OHLCV blank. Follows the gold (LBMA) trading calendar.
- Status: complete model-derived (derived leveraged dataset). Observed era now tracks UGL exactly.
- Segments:
  - `1970-01-02` to `2008-12-03` (UGL inception day): synthetic 2x daily-reset model from `GOLDPM`'s pure-spot **`Price Return`** (not Total Return, which now carries GLD's fee drag). `lev_ret = 2*u - 1*((^IRX/100 + 0.0093)*days/360) - 0.0095*days/365`. Flag `model_2x_daily_reset_synthetic_from_goldpm_spot_price_return_minus_financing_and_fee`.
  - UGL trading days after inception: observed UGL Yahoo adjusted-close daily total returns. Flag `observed_ugl_etf_adjusted_total_return`.
  - Observed era inherits GOLDPM's **NYSE calendar**, so every observed row is a UGL trading day; the holiday-flat path (`observed_ugl_us_holiday_flat`) is retained as a safety net but is 0 rows now.
- **Two bugs fixed 2026-06-20:** (1) holiday double-count (old build synthetic-filled US holidays AND let UGL's reopen span them → +33.8%/+1.89%/yr vs UGL); (2) calendar mismatch (London-calendar GOLD2X drifted ~+2%/yr vs UGL in a return-intersection backtest). Both resolved by GOLDPM's observed era moving to the NYSE calendar (GOLD2X inherits it). Observed era is now an exact constant multiple of UGL (regression-tested); script reproduces UGL with **0.000% gap**.
- Calibration: spread 0.93% over `^IRX` (absorbs gold futures roll/storage), validated on **clean LBMA-calendar** spot returns (cumulative ratio ~0.995). **Daily corr only ~0.67** because GOLDPM is the LBMA PM fix (~10:30am ET) and UGL closes 4pm ET — a timing basis. (The build's reported `calibration_vs_etf_overlap` ~1.33 is computed on the now-NYSE Price Return and is calendar-inflated; the LBMA-basis test is authoritative.)
- Build: 14,200 rows 1970-01-02 to 2026-06-18; synthetic 9,789, observed UGL 4,411, holiday-flat 0.
- Caveats: pre-2008 model-derived; LBMA spot underlying not UGL's futures benchmark; daily UGL alignment limited by timing; path-dependent. Worst day -27% (Jan 1980 gold crash).
- Build/update: `python src\build_gold_2x.py`; `python src\update_gold_2x.py` (refresh `GOLDPM` first).

## External Backtesting Script

Script path:

`the external backtesting application`

Custom dataset aliases currently supported there:

- `USLCAP`
- `GOLDPM`
- `STT`
- `ITT`
- `LTT`

The script has an early ticker/weight length validation check. If a config line uses `tickers, weights = ['LTT'], []`, it will fail clearly; correct form is `['LTT'], [1]`.

Fixed: the `STT` alias was registered as `"sTT"` (typo) in `CUSTOM_DATASETS`; corrected to `"STT"`.

The script was converted to UTF-8 after a Windows-1252 dash caused direct Python execution to fail.

## Documentation Map

- `PLAN.md`: project plan, milestones, dataset update principles.
- `LOG.md`: chronological implementation and decision log.
- `docs/dataset_methodologies.md`: per-dataset derivation methodology. Update this for every dataset.
- `docs/source_registry.md`: active, validation, candidate, blocked, and rejected sources.
- `docs/validation.md`: validation requirements and test categories.
- `sources/citations/`: source notes per dataset.
- `sources/manifests/`: dataset manifests and build metadata.

## Build And Test Commands

Run from:

`the repository root`

Build/update examples:

```text
python src\update_all_datasets.py
python src\update_all_datasets.py --dry-run --no-tests
python src\update_all_datasets.py --list-datasets
python src\build_gold.py
python src\update_gold.py
python src\build_long_term_us_treasury.py
python src\update_long_term_us_treasury.py
```

`src\update_all_datasets.py` is the preferred one-command refresh path. It runs all dataset update
scripts in dependency order, passes `--end-date` through to the underlying scripts, stops on the
first failure by default, prints row-count/date-range summaries, and runs the validation suite after
successful updates. Use `--no-tests` to skip validation, `--continue-on-error` to keep independent
updates running after a failure, and `--only`/`--skip` for targeted refreshes. A requested
`--end-date` is inclusive, but final rows can end earlier when the live source has not yet published
that date, when markets are closed, or when the source is monthly/static. `GLBOND` and `GLSTBOND`
reuse cached historical JST/BIS/OECD/MoF/BoE raw files by default; use
`--refresh-static-sources` only when intentionally refetching those heavy static inputs.

Validation:

```text
$env:PYTEST_DISABLE_PLUGIN_AUTOLOAD='1'; python -m pytest -q tests\validation
```

Last known full validation result:

```text
142 passed on 2026-06-28 after the all-dataset refresh continuation
```

Last all-dataset refresh state:

- Run date: 2026-06-28.
- Daily market datasets now end on `2026-06-26` (latest available Friday close for the Sunday run).
- `CPI` ends on `2026-06-28` because it is calendar-daily with latest monthly CPI carried forward.
- `GLBOND`/`GLSTBOND` update path verified after the cache fix: historical JST/BIS/OECD/MoF/BoE inputs loaded from cache and only live Yahoo ETF tails were refreshed.

## Git Workflow

Before edits:

```text
git status --short --branch
```

After meaningful changes:

```text
git add -A
git commit -m "<message>"
git push
```

Be aware that this environment may still patch files under the old locked `datasets` folder if using workspace-scoped patch tooling. Confirm active files are in `financial_datasets` before running tests or committing.

### CMDTY

- File: `data/processed/broad_commodities.csv`
- Alias in backtesting script: `CMDTY` (registered by the user in the portfolio script).
- Definition: DBC-like broad diversified commodity futures total-return series.
- `Close` / `Price Return`: normalized **excess-return** (spot+roll) level. Starts at 100 on 1970-01-02.
- `Adj Close` / `Total Return`: normalized **total-return** level (excess return + T-bill collateral). Starts at 100 on 1970-01-02. The backtester reads `Adj Close`.
- Status: complete model-derived public-source dataset. The 1970-1991 history is anchored to the **S&P GSCI Total Return** index (roll yield + collateral + GSCI production weights), rebuilt 2026-06-26.
- **GSCI TR anchor**: `sources/raw/broad_commodities_gsci_tr_macromicro.csv` is a **static committed file** - the S&P GSCI Total Return Index (base 100 at 1970-01-02), republished by MacroMicro at ~bi-monthly resolution (358 points), extracted in-browser because free daily GSCI TR is paywalled everywhere. It is historical and does not change; the build reads it (it cannot be refetched programmatically). Only the DBC tail updates live.
- Segments:
  - `1970-01-02` to `1984-01-03`: GSCI TR anchor log-linearly smoothed to daily `^IRX` dates. Adds roll + collateral + GSCI composition vs the old World Bank model; **daily volatility is smoothed** (no free daily broad-commodity data exists pre-1984). Flag `model_gsci_total_return_anchor_smoothed_daily`.
  - `1984-01-04` to `1991-01-02`: Yahoo `^SPGSCI` spot daily **shape** overlaid per anchor interval to the GSCI TR anchor - injects the ~9%/yr roll + ~7%/yr collateral the spot index omits while keeping genuine daily moves (~16%/yr vol). Flag `model_gsci_total_return_anchor_with_spgsci_spot_daily_shape`.
  - `1991-01-03` to `2006-02-06`: Yahoo `^BCOM` (Bloomberg Commodity Excess Return = spot+roll) + Yahoo `^IRX` T-bill collateral. Verified as Excess Return by 2021 annual return check. Unchanged.
  - `2006-02-07` to present: Yahoo `DBC` observed ETF total return. Unchanged. ~0.89%/yr expense drag.
- Validation: GSCI TR grew 3.08x vs `^SPGSCI` spot 1.04x over 1984-91 (=> ~9%/yr roll yield); 3.06x vs `^BCOM` ER 1.83x over 1991-2006. Adj Close tracks the anchor within ~2% at sample dates.
- Caveats:
  - Segments 0-1 anchored to a **downsampled** GSCI TR republication (not licensed daily). Adj Close tracks the index within a few percent; Segment 0 daily vol is smoothed; Segment 1's daily shape is `^SPGSCI` spot.
  - GSCI is more energy-heavy than DBC and back-tested before its 1991 launch.
  - Segment 2 (`^BCOM`) treated as excess return by annual-return behavior (no licensed Bloomberg metadata).
  - Segment 3 is DBC ETF net return, not gross index return.
  - 1991 and 2006 boundaries are methodology breaks (the 1984 boundary is now internal to the GSCI reconstruction). Levels continuous, exposure not.
  - `Open`, `High`, `Low`, `Volume` blank for model/index segments.
- Current build: 14,163 rows from `1970-01-02` to `2026-06-25`; segment counts GSCI-smoothed 3,487, GSCI-shape 1,768, BCOM 3,781, DBC 5,127.
- Future upgrade: licensed **daily** S&P GSCI Total Return (removes the smoothing) or a constituent-level futures reconstruction phasing energy in as contracts launched.

### CPI

- File: `data/processed/cpi_inflation.csv`
- Alias in portfolio script: `CPI` (used internally as the inflation deflator).
- Definition: U.S. CPI-U, all urban consumers, U.S. city average, all items, seasonally adjusted (`CUSR0000SA0`).
- `Close == Adj Close`: CPI-U index level, 1982-84=100.
- Status: complete model-derived daily deflator from monthly BLS CPI.
- Method: exact BLS month-start values, constant log interpolation between adjacent monthly CPI observations, and carry-forward after the latest published month.
- Caveat: BLS CPI is monthly. Daily rows are for smooth inflation-adjusted plotting and are not observed daily inflation prints.

### GLSTOCK

- File: `data/processed/global_stocks.csv`
- Alias in portfolio script: `GLSTOCK`
- Definition: global all-world equity total-return proxy, akin to VT / MSCI ACWI / FTSE All-World.
- `Close == Adj Close`: normalized total-return proxy level.
- Status: complete model-derived public-source proxy.
- Segments:
  - `1970-01-02` to `1989-12-29`: USLCAP daily path scaled so each calendar year matches public MSCI World gross annual total return.
  - `1990-01-02` to `1990-06-29`: USLCAP daily gap fill before French developed-market daily data starts.
  - `1990-07-02` to `2008-06-26`: Kenneth French Developed 3 Factors daily total return (`Mkt-RF + RF`).
  - From `2008-06-27`: observed VT adjusted-close total returns via Yahoo.
- Caveat: early history is not observed daily all-world index history; 1990-2008 is developed markets only; VT introduces ETF net-return/expense effects.

### GLBOND

- File: `data/processed/global_bonds.csv`
- Alias in portfolio script: `GLBOND`
- Definition: unhedged global bond total-return proxy in USD.
- `Close == Adj Close`: normalized total-return proxy level.
- Status: complete model-derived public-source proxy.
- Segments:
  - `1970-01-02` to `2007-10-10`: JST-anchored daily reconstruction. Daily path = GDP-weighted basket (16 advanced economies, weighted by comparable real GDP `rgdpmad`x`pop`) of observed daily FX (BIS `WS_XRU`, local currency per USD) and bond total returns, then a per-year multiplicative overlay so each calendar year compounds exactly to the JST annual basket. Bond returns are **daily** for US (in-repo 7-10y Treasury TR, 1970+), Japan (MoF 10y JGB, 1986-07+) and UK (BoE 10y nominal spot, 1979+) — ≈62% of the basket from 1979 — and **monthly** (OECD MEI `IRLTLT01` par-bond reprice, smoothed within month) for the rest. Flag `model_jst_anchored_daily_fx_monthly_yield_global_govt_bond_unhedged`. BIS/OECD via DBnomics (key-less); MoF/BoE are bespoke fetches.
  - From `2007-10-12`: observed daily 45% BND / 55% BWX adjusted-close blend, rebalanced daily. BWX provides unhedged international local-currency bond exposure.
- **De-smoothing (2026-06-19):** the early segment previously spread one JST annual return across the whole year with a constant daily log return (all pre-2007 intra-year structure was artificial). It now carries a genuine daily path (FX daily for all 16; rate daily for US/JP/UK): early-segment annualized vol ~5.9% (was ~0 within-year), >=247 distinct daily returns per year (was 1), correctly-timed events (Plaza Accord 1985-09-23, Carter dollar-rescue 1978-11-02, 1987 and 1994 US bond moves). JST annual returns preserved exactly via the overlay (invariant ~1.2e-9). GDP-weighting bug fixed the same day (real GDP, not nominal `gdp`/`xrusd`).
- Update behavior: ordinary daily updates reuse cached JST/BIS/OECD/MoF/BoE historical raw files and refresh only the BND/BWX Yahoo tail. Run `python src\update_global_bonds.py --refresh-static-sources` only to refetch the heavy historical inputs.
- Caveats:
  - **1970-2007 is still model-derived.** The annual *level* is anchored to JST; the daily *path* uses observed daily FX (all countries) and observed bond returns. The rate leg is daily only for US (1970+), UK (1979+) and Japan (1986-07+); other countries and earlier years use monthly OECD yields smoothed within month, so their daily rate moves are not captured.
  - **The early segment is government-bond-only and advanced-economy-only** (16 countries with valid JST data). It is not a full global aggregate with corporate, securitized, emerging-market, or inflation-linked bonds.
  - **Currency exposure is intentionally unhedged.** FX is daily (BIS) in the path and annual (JST `xrusd`) in the anchor.
  - **Rate coverage is staged.** US daily from 1970, UK from 1979, Japan from 1986-07; before those, and for all other countries, the rate leg is monthly (Italy/Spain/Nordics basket-proxied until their OECD yield begins). All carry daily FX. So 1970-79 has only the US on a daily rate leg.
  - **US daily rate leg is ~8.5y** (in-repo ITT) vs 10y par model for UK/Japan/others — immaterial, absorbed by the overlay.
  - **Weights are modeled.** Country weights use prior-year comparable real GDP (`rgdpmad` x `pop`, 1990 international dollars), not market value of investable bond debt. (Originally weighted by JST nominal `gdp`/`xrusd`, which was wrong because JST `gdp` units are inconsistent across countries — fixed 2026-06-19; see LOG.)
  - **The 2007 splice changes methodology.** The observed segment is a fixed 45% BND / 55% BWX daily-rebalanced blend, not an official global aggregate index; it excludes international corporate/securitized bonds.
  - **Licensing matters.** JST has non-commercial license terms; review before redistributing derived data outside this project.
  - Preferred future upgrade: licensed unhedged FTSE WGBI / Bloomberg Global Aggregate daily history, or daily per-country sovereign yields for the remaining markets (Germany, Canada, France, Italy, …) back to the 1970s to extend the daily rate leg beyond the current US/UK/Japan ≈62%. Germany was investigated: free daily yields reach only 1997.

### GLSTBOND

- File: `data/processed/global_short_term_bonds.csv`
- Alias in portfolio script: `GLSTBOND` (not yet registered in the portfolio script).
- Definition: unhedged global **short-term (1-3yr)** government-bond total-return proxy in USD.
  ISHG-like in maturity but **global incl. US** (the short-duration sibling of `GLBOND`).
- **`Close` / `Price Return` = GROSS of fees; `Adj Close` / `Total Return` = NET** of a
  representative ~0.26%/yr fund expense drag (`Adj Close != Close`). The backtester reads
  `Adj Close`, so it gets an investable, net-of-fee series.
- Status: complete model-derived public-source proxy.
- Segments:
  - `1970-01-02` to `2009-01-29`: **direct** daily reconstruction (no JST overlay). GDP-weighted
    16-country basket of daily BIS FX x a constant-maturity 2yr par-bond TR. 2yr yield is daily
    for US (in-repo STT, 1970+), Japan (MoF 2yr JGB, **1974-09**+) and UK (BoE 2yr, 1979+);
    monthly elsewhere (OECD 3-mo + 10y interpolated to 2yr, JST `stir`/`ltrate` early fallback).
    Net leg subtracts the modeled fee. Flag `model_direct_daily_fx_2y_yield_global_short_govt_bond_unhedged_net_of_fee`.
  - From `2009-01-30`: observed GDP-weighted blend `w_us`*SHY + `(1-w_us)`*mean(ISHG, BWZ),
    annually rebalanced (`w_us` = US share of developed real GDP, 0.20->0.46, carried forward
    past JST). Flag `observed_shy_ishg_bwz_gdp_weighted_short_govt_bond_unhedged_net_of_fee`.
- Build: 14,233 rows 1970-01-02 to 2026-06-15; model 9,864, observed 4,369.
- **Key difference from GLBOND**: no JST annual overlay (JST `bond_tr` is a 10yr return, wrong
  for a 1-3yr series; short bonds are carry-dominated). Japan's daily short leg starts 1974 (vs
  1986 for the 10yr). Modeled fees introduced (GLBOND has none).
- Caveats: 1970-2009 model-derived; 2yr yield interpolated from 3-mo/10y where no true 2yr
  exists; rate leg daily only for US/JP/UK, monthly elsewhere; advanced-economy government-bonds
  only; observed blend is a GDP-weighted SHY+ISHG/BWZ proxy, not an official index; GDP (not
  market-cap-of-debt) weights; single representative fee.
- Build/update: `python src\build_global_short_term_bonds.py`; `python src\update_global_short_term_bonds.py` (refresh `STT` first).
- Update behavior: ordinary daily updates reuse cached JST/BIS/OECD/MoF/BoE historical raw files and refresh only the SHY/ISHG/BWZ Yahoo tail. Run `python src\update_global_short_term_bonds.py --refresh-static-sources` only to refetch the heavy historical inputs.
- Remaining: register `GLSTBOND` alias in the portfolio script.

## To-Do

- **Alias registration**: `CMDTY`, `USLCAP3X`, `LTT3X`, and `ITT3X` aliases have been registered by the user in `external backtesting application`.
- **Register `GOLD2X` alias in `external backtesting application`** — add `GOLD2X` → `gold_2x.csv` to `CUSTOM_DATASETS`.
- **Next derived leveraged dataset**: remaining 2x tiers — SSO (2x) from `USLCAP`, UBT (2x) from `LTT`, ITT2X/UST (2x) from `ITT`. Reuse the `build_gold_2x.py` / `build_intermediate_treasury_3x.py` pattern (change `LEVERAGE`, base, ETF symbol, ER, calibrate the spread). Watch for: thin-ETF stale-price noise (as with TYD) and timing-basis decorrelation (as with GOLD2X) when validating.
- After that: U.S. TIPS and Cash/T-Bills. Initial Inflation/CPI support is complete as `CPI`;
  future work may add alternative inflation measures.

### Derived Leveraged Dataset Backlog

Goal: create long-horizon daily synthetic leveraged datasets that mimic common leveraged ETFs before their live inception dates, using the project's existing 1970+ base datasets as the underlying exposures.

- **3x U.S. large cap / UPRO-like**: DONE. Built as alias `USLCAP3X` (`data/processed/us_large_cap_3x_sp500.csv`). Synthetic 3x daily-reset from `USLCAP` total return (1970→UPRO inception) + observed UPRO returns; financing `^IRX`+0.65% spread (actual/360), fee 0.91% (actual/365); calibrated to UPRO overlap (corr 0.998, cum ratio ~1.0). Remaining: register `USLCAP3X` in `external backtesting application`. This is the reference pattern for the other leveraged tiers below.
- **3x long Treasury / TMF-like**: DONE. Built as alias `LTT3X` (`data/processed/long_term_us_treasury_3x.csv`). Synthetic 3x daily-reset from `LTT` total return (1970→TMF inception 2009-04-16) + observed TMF; financing `^IRX`+0.53% spread (actual/360), fee 1.06% (actual/365); calibrated to TMF overlap (corr 0.997, cum ratio ~1.0). Duration mismatch documented (pre-2002 LTT is Fed 25y par + VUSTX, not the ICE 20+ Year index). Remaining: register `LTT3X` in `external backtesting application`.
- **2x long Treasury / UBT-like**: derive from `LTT` total-return daily returns. Target alias candidate: `LTT2X` or `UBTX`. Validate live overlap against UBT where usable.
- **3x intermediate Treasury / TYD-like**: DONE. Built as alias `ITT3X` (`data/processed/intermediate_term_us_treasury_3x.csv`). Synthetic 3x daily-reset from `ITT` total return (1970→TYD inception 2009-04-16) + observed TYD; financing `^IRX`+0.19% spread (actual/360), fee 1.09% (actual/365); calibrated to TYD cumulative growth (ratio ~1.0). NOTE: the genuine 3x 7-10yr ETF is Direxion TYD, not UST — the earlier "3x UST" label was wrong.
- **2x intermediate Treasury / UST-like**: derive from `ITT` total-return daily returns. Target alias candidate: `ITT2X`. Validate live overlap against **UST** (ProShares Ultra 7-10 Year Treasury, the genuine 2x fund) adjusted-close returns after inception (2010-01).
- **2x gold / UGL-like**: DONE. Built as alias `GOLD2X` (`data/processed/gold_2x.csv`). Synthetic 2x daily-reset from `GOLDPM` LBMA PM spot (1970→UGL inception 2008-12-03) + observed UGL; financing `^IRX`+0.93% spread (actual/360, spread absorbs gold futures roll/storage), fee 0.95% (actual/365); calibrated to UGL cumulative growth (ratio ~1.0). Base is LBMA spot (decided against GLD); daily UGL correlation limited (~0.67) by LBMA-fix vs US-close timing — validated via cumulative + volatility, with GLD as a timing cross-check. Remaining: register `GOLD2X` in `external backtesting application`.
- **Potential commodity leverage**: derive 2x or 3x versions from `CMDTY` only after the CMDTY alias is registered and the gap caveats are accepted. Because CMDTY has source-family breaks and modelled early history, leveraged commodity variants need especially prominent quality flags.

Implementation notes for all leveraged datasets:

- Use daily reset arithmetic: model return = leverage multiple * underlying daily total return minus daily financing/expense drag, then compound.
- Keep the leveraged series separate from base datasets; do not overwrite existing asset-class files.
- Add distinct `Quality Flag` values for synthetic pre-inception history and observed ETF validation periods.
- Document assumptions for financing rate, management fee, swap/futures tracking drag, borrowing spread, and the handling of non-positive model levels in extreme drawdowns.
- Add validation tests comparing live overlap daily returns and cumulative performance against the real ETF where public Yahoo adjusted-close data exists.
- Update `docs/dataset_methodologies.md`, per-dataset methodology docs, source registry, validation docs, citations, manifests, and backtesting aliases for each derived dataset.

## Near-Term Implementation Notes

- Always update `PLAN.md`, `LOG.md`, `docs/dataset_methodologies.md`, `docs/source_registry.md`, `docs/validation.md`, citations, manifests, and tests for each dataset.

### Open Questions

- No blocking CMDTY source-type question remains. `^BCOM` is documented as Bloomberg Commodity Excess Return based on the 2021 annual-return check.
