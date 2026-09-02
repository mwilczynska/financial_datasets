# Project Log

## 2026-06-28 - GLBOND/GLSTBOND daily updater cache fix

- Followed up on the first live `src/update_all_datasets.py` run hanging at `GLBOND` with no output after the first eight datasets completed.
- Root cause: `build_global_bonds.py` and `build_global_short_term_bonds.py` refetched heavy historical inputs before printing anything: JST workbook, 15 BIS FX DBnomics series, OECD monthly yield series, MoF JGB CSV, and the ~39 MB BoE GLC archive. These inputs drive historical pre-2007/pre-2009 reconstruction and do not need to be refetched on every daily tail refresh.
- Changed both global bond builders to reuse cached JST/BIS/OECD/MoF/BoE raw files in `sources/raw/` by default, print each phase with `flush=True`, and refresh only the live Yahoo ETF tails during ordinary updates.
- Added `--refresh-static-sources` to `build_global_bonds.py`, `build_global_short_term_bonds.py`, and `update_all_datasets.py` for explicit historical-source refreshes.
- Updated `src/README.md`, `HANDOVER.md`, `docs/methodology_glbond.md`, `docs/methodology_glstbond.md`, and `AGENTS.md` to document the cache behavior and the explicit static-source refresh option.
- Verified the fixed path by continuing the interrupted run for `GLBOND`, `GLSTBOND`, `USLCAP3X`, `LTT3X`, `ITT3X`, and `GOLD2X`. `GLBOND` and `GLSTBOND` used cached historical sources immediately, refreshed only live Yahoo tails, and completed in about 5 seconds each.
- The processed suite is now refreshed to the latest available observations as of the `2026-06-28` run: daily market datasets end `2026-06-26`; `CPI` ends `2026-06-28`. Full validation after the continuation: `142 passed`.

## 2026-06-28 - All-dataset update orchestrator

- Added `src/update_all_datasets.py`, a single command that refreshes the processed dataset suite in dependency order by delegating to each existing per-dataset update script.
- The update order now runs base datasets first (`USLCAP`, Treasuries, `GOLDPM`, `CMDTY`, `CPI`), then dependent global blends (`GLSTOCK`, `GLBOND`, `GLSTBOND`), then derived leveraged datasets (`USLCAP3X`, `LTT3X`, `ITT3X`, `GOLD2X`).
- The script accepts `--end-date`, `--root`, `--overlap-days`, `--only`, `--skip`, `--continue-on-error`, `--dry-run`, `--list-datasets`, and `--no-tests`. It stops on the first failure by default so derived datasets are not rebuilt from stale base datasets.
- After successful updates it prints a row-count/date-range summary and runs `$env:PYTEST_DISABLE_PLUGIN_AUTOLOAD='1'; python -m pytest -q tests/validation` by default.
- Documented the updater in `AGENTS.md`, `src/README.md`, `HANDOVER.md`, `PLAN.md`, and `docs/validation.md`, including the caveat that "current" means latest available source observation, not necessarily a row dated the requested `--end-date` on weekends, market holidays, delayed monthly sources, or static anchors.
- Verified the new script with `python -m py_compile src/update_all_datasets.py`, `python src/update_all_datasets.py --list-datasets`, and `python src/update_all_datasets.py --dry-run --no-tests`.

## 2026-06-26 - CMDTY rebuilt on S&P GSCI Total Return anchor (roll yield + collateral, de-smoothed 1984-91)

Systematically patched the weakest CMDTY segments. The old 1970-1991 history was the worst part
of the dataset: Segment 0 (1970-1983) was a World Bank **monthly spot** model (no roll yield,
daily-smoothed, energy-light export-value weights), and Segment 1 (1984-1991) was **GSCI spot
only** (no roll). Both are now anchored to the **S&P GSCI Total Return** index.

**What changed:**

- New static source `sources/raw/broad_commodities_gsci_tr_macromicro.csv`: the S&P GSCI Total
  Return Index, base 100 at 1970-01-02, 358 points (~bi-monthly), 1970-2026. Free programmatic
  GSCI TR is paywalled everywhere (Yahoo `^SPGSCITR` empty, FRED/DBnomics none, Investing.com and
  Barchart blocked); extracted in-browser (Claude-in-Chrome) from MacroMicro's Highcharts object.
- `src/build_broad_commodities.py`: Segment 0 (1970-1983) now log-linearly smooths the GSCI TR
  anchor onto `^IRX` dates (no free daily broad-commodity data exists pre-1984). Segment 1
  (1984-1991) overlays the genuine daily `^SPGSCI` spot **shape** onto the anchor per anchor
  interval (the `GLSTOCK`/`GLBOND` de-smoothing pattern), injecting the missing roll + collateral
  while restoring ~16%/yr daily volatility. Segments 2 (BCOM+IRX) and 3 (DBC) unchanged. Column
  convention clarified: `Close`/`Price Return` = excess return (spot+roll); `Adj Close`/`Total
  Return` = total return (excess + collateral), derived by stripping daily `^IRX` for the
  GSCI segments. World Bank fetch/parse removed from the active build path.
- New flags `model_gsci_total_return_anchor_smoothed_daily` (Seg 0) and
  `model_gsci_total_return_anchor_with_spgsci_spot_daily_shape` (Seg 1).

**Why GSCI TR (energy-tilted) over AQR equal-weight (also free):** user wanted DBC-like exposure;
GSCI is production-weighted and energy-heavy (closest to DBC in spirit). AQR's roll-inclusive
monthly TR (1877+) is freely downloadable but equal-weighted, so it was documented and rejected.

**Why 1970-1983 stays smoothed:** no free daily broad-commodity data exists before 1984 (Yahoo
individual futures start ~2000; Stooq archive 1985-10, no grains; energy futures didn't even exist
- WTI 1983, natgas 1990, COMEX gold Dec 1974). Roll yield requires futures-curve data, unavailable
for free pre-1990. So the honest choice was to fix the *level* (roll+collateral+composition) and
leave 1970-83 daily vol smoothed rather than fabricate it.

**Validation:** GSCI TR grew 3.08x vs `^SPGSCI` spot 1.04x over 1984-1991 - collateral (~7.3%/yr)
explains ~1.64x, the residual ~1.8x implies ~9%/yr roll yield (energy-heavy backwardation),
confirming the old spot-only segment understated the era ~3x. Over 1991-2006 GSCI TR 3.06x vs
`^BCOM` ER 1.83x (~1.67x = collateral + GSCI energy tilt), consistent. Build: 14,163 rows
1970-01-02 to 2026-06-25 (GSCI_SMOOTH 3,487 / GSCI_SHAPE 1,768 / BCOM 3,781 / DBC 5,127). Adj
Close tracks the anchor within ~2% at sample dates; Seg 1 vol 15.7%/yr (was ~0). Tests rewritten
(12 CMDTY tests); full suite 142 passed.

**Caveats preserved:** anchor is a downsampled republication (not licensed daily); Seg 0 daily vol
smoothed; Seg 1 daily shape is spot; GSCI is energy-heavier than DBC and back-tested pre-1991;
1991 and 2006 remain methodology breaks. Future upgrade: licensed daily GSCI TR or a
constituent-level futures reconstruction.

## 2026-06-21 - GLSTBOND (ISHG-like Global Short-Term Govt Bonds) Built

Built a global short-term (1-3yr) government-bond total-return proxy back to 1970 - ISHG-like
in maturity but global in scope (includes the US, per user request), the short-duration sibling
of `GLBOND`.

**What was built:**

- `src/build_global_short_term_bonds.py` (fork of `build_global_bonds.py`) and
  `src/update_global_short_term_bonds.py`.
- `data/processed/global_short_term_bonds.csv` / `.parquet`: 14,233 rows, 1970-01-02 to
  2026-06-15. Model segment 9,864; observed segment 4,369 (blend from 2009-01-30).
- Manifest, build metadata, citation, methodology (`docs/methodology_glstbond.md`),
  index/source-registry/validation/PLAN/HANDOVER updates, and tests
  (`tests/validation/test_global_short_term_bonds_contract.py`, 13 tests). Full suite: 141 passed.

**Source verification (done first, de-risked the build):**

- MoF JGB file publishes the 1-9yr nodes from **1974-09-25** - so Japan's daily 2yr leg starts
  twelve years before its 10yr (1986), a major early-coverage gain over GLBOND.
- OECD `IR3TIB01` (3-mo) + `IRLTLT01` (10y) give a 2yr point by interpolation; coverage is
  patchy pre-1980 for several countries, so JST annual `stir`/`ltrate` (confirmed in percent)
  backstop the early gaps. ISHG 2009-01-28, BWZ 2009-01-30, SHY 2002-07 on Yahoo.

**Method and decisions:**

- **Maturity:** constant-maturity 2yr par bond (`BOND_MATURITY_YEARS = 2.0`); the MoF/BoE
  parsers already read the whole curve, so re-pointing to the 2yr node was a one-line change.
- **Anchor:** *direct construction, no JST overlay.* JST `bond_tr` is a 10yr long-bond return
  (wrong level for a 1-3yr series) and short bonds are carry-dominated, so the daily path is
  compounded as-is. JST contributes only GDP weights + the pre-OECD short-rate fallback.
- **2yr yield:** linear-in-maturity interpolation between the OECD 3-month and 10-year rates
  (0.25y/10y nodes -> 2y); JST annual fallback before OECD coverage.
- **Daily rate legs:** US in-repo STT (2yr) 1970+, Japan MoF 2yr 1974-09+, UK BoE 2yr 1979+.
- **Modeled fees (user request):** `Close`/`Price Return` gross; `Adj Close`/`Total Return` net
  of a representative ~0.26%/yr drag (blended SHY 0.15% + ISHG/BWZ 0.35% at GDP weights). Model
  era subtracts the fee; observed era (already net via Yahoo adj close) adds it back to keep
  Close gross. Measured implied drag: 0.2605%/yr.
- **Observed blend (user request - not fixed 50/50):** `w_us`*SHY + `(1-w_us)`*mean(ISHG,BWZ),
  where `w_us` is the US share of developed-market real GDP each year (0.20 in 1870 → 0.46 by
  2026), annually rebalanced and carried forward past JST's last year.

**Validation:** 0 return-arithmetic mismatches on both columns; observed blend reproduced
exactly (tol 1e-10); model-era vol 5.1% (below GLBOND's 5.9% - shorter duration); ~252 distinct
daily returns/year; Plaza/Carter FX shocks correct.

**Remaining:** register the `GLSTBOND` alias in the portfolio script (user step). Future
upgrades: market-cap (investable debt) weighting; licensed FTSE WGBI Developed 1-3yr daily;
daily 2yr yields for Germany/Canada/France/etc. to extend the daily rate leg beyond US/JP/UK.

## 2026-06-17 - GOLD2X (UGL-like 2x Gold) Derived Dataset Built

Built the fourth derived leveraged dataset and the first 2x one: a 2x daily-reset gold total-return series modeling ProShares Ultra Gold (`UGL`) back to 1970.

**What was built:**

- `src/build_gold_2x.py` and `src/update_gold_2x.py`.
- `data/processed/gold_2x.csv` / `.parquet`: 14,175 rows, 1970-01-02 to 2026-06-15. Synthetic 9,883 rows (incl. ~97 post-inception US-holiday fills); observed UGL 4,292 rows. UGL inception 2008-12-03.
- Manifest, build metadata, citations, methodology (`docs/methodology_gold2x.md`), index/source-registry/validation updates, and tests (`tests/validation/test_gold_2x_contract.py`, 11 tests).

**Method and decisions:**

- Reused the daily-reset pattern with L=2 and the `GOLDPM` (LBMA PM spot) base: `lev_ret = 2*u - 1*((^IRX/100 + spread)*days/360) - 0.0095*days/365`.
- **Timing-basis finding**: default build gave daily UGL correlation only 0.67 (ann. TE ~28%), roughly constant across all years, with model/UGL volatilities matching (~2% each). Diagnosed as a clock-offset: GOLDPM is the LBMA PM fix (~10:30am ET) while UGL closes at 4pm ET. Confirmed by fetching GLD: **UGL daily returns vs 2x-GLD correlate at 0.997** (both US close), while **LBMA PM-fix vs same-day GLD correlate at only 0.66**. So the model logic is correct; only the gold base's clock-time differs from UGL.
- **Calibration**: targeted cumulative growth (robust to timing noise). Spread 0.40% left model +9.6% vs UGL; raised to **0.93%** for cumulative ratio 1.0007. The larger spread (vs Treasury funds) also absorbs gold futures roll/storage — UGL (futures-based Bloomberg Gold Subindex) ran below 2x-spot, consistent with contango.
- **Calendar handling**: kept the gold (LBMA) trading calendar throughout. ~97 post-inception LBMA-open/US-closed holidays (MLK, Presidents Day, July 3, Labor Day, Thanksgiving, etc.) have no UGL price and are filled with the synthetic model (flagged); observed returns compute against the most recent UGL close. This means the observed era has interspersed synthetic rows and many flag transitions — tests assert the bounded count (<150) rather than a single transition.
- Worst day -27% (Jan 1980 gold crash, 2x), max +27% (Jan 1980 spike); `-0.9999` floor never triggers.

**Caveats:** pre-2008 model-derived; LBMA-spot underlying not UGL's futures benchmark; daily UGL alignment limited (~0.67) by timing basis (cumulative/vol sound); path-dependent. Tests calibrate/validate on cumulative growth + volatility ratio, not daily correlation.

**Next:** 2x equity/Treasury tiers (SSO from USLCAP, UBT from LTT, ITT2X/UST from ITT).

## 2026-06-17 - ITT3X (TYD-like 3x Intermediate Treasury) Derived Dataset Built

Built the third derived leveraged dataset: a 3x daily-reset intermediate-term (7-10 year) Treasury total-return series modeling Direxion Daily 7-10 Year Treasury Bull 3X Shares (`TYD`) back to 1970.

**Naming correction:** the backlog labelled "UST" as the 3x intermediate-Treasury ETF, but UST (ProShares Ultra 7-10 Year Treasury) is a **2x** fund. The genuine 3x 7-10yr ETF is Direxion **TYD**, used here as the calibration/validation target. Confirmed the choice with the user, built as alias `ITT3X` validated against TYD, and corrected the swapped UST/TYD leverage labels in PLAN.md and HANDOVER.md (UST → future `ITT2X` 2x target).

**What was built:**

- `src/build_intermediate_treasury_3x.py` and `src/update_intermediate_treasury_3x.py`.
- `data/processed/intermediate_term_us_treasury_3x.csv` / `.parquet`: 14,158 rows, 1970-01-02 to 2026-06-15. Synthetic 9,841 rows; observed TYD 4,317 rows. TYD inception 2009-04-16.
- Manifest, build metadata, citations, methodology (`docs/methodology_itt3x.md`), index/source-registry/validation updates, and tests (`tests/validation/test_intermediate_treasury_3x_contract.py`, 11 tests).

**Method and decisions:**

- Reused the `LTT3X`/`USLCAP3X` daily-reset pattern with the `ITT` base: `lev_ret = 3*u - 2*((^IRX/100 + spread)*days/360) - 0.0109*days/365`. Financing `^IRX` actual/360, TYD ER 1.09% actual/365.
- **TYD data-quality finding**: with default spread the model matched TYD's daily returns at 0.94-0.996 correlation in 2009-2013 and 2019-2026, but only 0.37-0.66 in 2014-2018 (full-overlap corr 0.88, ann. TE ~10%). Year-by-year diagnosis showed this is TYD's thin trading / stale low-AUM Yahoo closes mid-decade, not a model error. Cumulative growth is robust to this mean-reverting noise, so calibration targets cumulative ratio; daily fidelity is validated on the clean 2019+ era.
- **Calibration**: spread 0.40% left the model 7% *below* TYD (opposite direction from TMF, because intermediate Treasuries are lower-vol with less decay and TYD's actual cumulative is higher). Lowered the spread to **0.19%**, giving cumulative ratio 0.9998. The low implied spread partly reflects TYD fee waivers.
- The synthetic 2009 level (~5,000) is far above LTT3X's (~650): intermediate Treasuries were much less volatile than long bonds through the 1970s-80s rate spikes, so 3x compounding decayed far less — a clean illustration of volatility-dependent leverage decay.

**Caveats:** pre-2009 is model-derived; observed segment inherits TYD's 2014-2018 stale-price noise; pre-2002 underlying is a Fed 8.5yr par model + VFITX, not the ICE 7-10yr index; path-dependent, not a simple 3x multiple.

**Next:** 2x tiers (SSO from USLCAP, UBT from LTT, UST/ITT2X from ITT), then UGL 2x gold from GOLDPM.

## 2026-06-17 - LTT3X (TMF-like 3x Long Treasury) Derived Dataset Built

Built the second derived leveraged dataset: a 3x daily-reset long-term Treasury total-return series modeling Direxion Daily 20+ Year Treasury Bull 3X Shares (`TMF`) back to 1970.

**What was built:**

- `src/build_long_term_treasury_3x.py` and `src/update_long_term_treasury_3x.py`.
- `data/processed/long_term_us_treasury_3x.csv` / `.parquet`: 14,174 rows, 1970-01-02 to 2026-06-15. Synthetic 9,857 rows; observed TMF 4,317 rows. TMF inception 2009-04-16.
- Manifest, build metadata, citations, methodology (`docs/methodology_ltt3x.md`), index/source-registry/validation updates, and tests (`tests/validation/test_long_term_treasury_3x_contract.py`, 11 tests).

**Method and decisions:**

- Reused the `USLCAP3X` daily-reset pattern with the `LTT` base as the underlying total return: `lev_ret = 3*u - 2*((^IRX/100 + spread)*days/360) - 0.0106*days/365`. Financing benchmark `^IRX` (actual/360), TMF expense ratio 1.06% (actual/365), calendar-day carry.
- `Close == Adj Close` (single 3x TR NAV normalized to 100); OHLCV blank. Synthetic through and including TMF inception day (2009-04-16); observed TMF adjusted-close returns from 2009-04-17.
- **Calibration**: spread 0.40% ran +4.7% cumulative vs TMF; settled on **0.53%**, matching TMF cumulative growth to ~0.04% (ratio 1.00035), daily correlation 0.997, ann. TE ~3.7%. In the overlap the LTT underlying is TLT-based, so the model-3x vs TMF-3x comparison is clean.
- Worst leveraged day ≈ -18% (1985-11-25, inherited from the LTT Fed-model `SVENY25`/`^TYX` switch region); the `-0.9999` floor never triggers.

**Caveats:** pre-2009 is model-derived, not observed TMF history. The key extra caveat vs USLCAP3X is the **duration/exposure mismatch**: TMF tracks the ICE 20+ Year index, but the LTT underlying only matches that from 2002 (TLT); before 2002 it is a Fed 25-year par model and VUSTX. TMF's cumulative total return over the 2009-2026 rising-rate overlap is well below 1.0 — a direct illustration of leverage decay; the series is path-dependent and not a simple 3x multiple of long-horizon returns.

**Next:** register `LTT3X` in `external backtesting application`; then 2x tiers (SSO from USLCAP, UBT from LTT) and intermediate-Treasury leverage (UST/TYD from ITT).

## 2026-06-17 - USLCAP3X (UPRO-like 3x Large Cap) Derived Dataset Built

Built the first derived leveraged dataset: a 3x daily-reset S&P 500 total-return series modeling ProShares UltraPro S&P500 (`UPRO`) back to 1970.

**What was built:**

- `src/build_us_large_cap_3x_sp500.py` and `src/update_us_large_cap_3x_sp500.py`.
- `data/processed/us_large_cap_3x_sp500.csv` / `.parquet`: 14,234 rows, 1970-01-02 to 2026-06-15. Synthetic 9,966 rows; observed UPRO 4,268 rows.
- Manifest, build metadata, citations, methodology (`docs/methodology_uslcap3x.md`), index/source-registry/validation updates, and tests (`tests/validation/test_us_large_cap_3x_contract.py`, 11 tests).

**Method and decisions:**

- Underlying daily return is the `USLCAP` `Total Return` column (S&P 500 total return), not price return, because UPRO's swap/NAV reflects index dividends.
- Daily-reset model: `lev_ret = 3*u - 2*((IRX/100 + spread)*days/360) - 0.0091*days/365`. Financing benchmark is Yahoo `^IRX` (13-week T-bill), accrued actual/360 on the 2x borrowed exposure; expense ratio 0.91% accrued actual/365; calendar-day gaps capture weekend/holiday carry.
- `Close == Adj Close` (single total-return NAV normalized to 100); `Price Return == Total Return`. A synthetic daily-reset leveraged fund has no separate price index. OHLCV blank.
- Synthetic segment runs 1970-01-02 through and including UPRO's first trading day (2009-06-25); observed UPRO adjusted-close returns apply from the next day so every observed row has a prior UPRO value. Levels compound continuously across the boundary.
- **Calibration**: the borrowing spread is the single free parameter. Started at 0.40% (model ran ~3 bps/day hot, +9% cumulative vs UPRO); zeroing the mean daily diff (0.77%) overshot to -4% cumulative due to path/volatility effects. Settled on 0.65%, which matches cumulative UPRO growth over 2009-2026 to within ~0.01% (ratio 0.99994), with daily correlation 0.998 and ~3.2% annualized tracking error (inherent to daily-reset modeling).
- Worst leveraged day (1987-10-19, ≈ -57%) survives positive; a `-0.9999` floor guards non-positivity but never triggers.

**Caveats:** pre-2009 is model-derived, not observed UPRO history; assumes constant spread and a T-bill financing proxy (true swap rate is closer to fed funds + counterparty spread); inherits the pre-1988 CRSP large-cap proxy in `USLCAP`; path-dependent and not a simple 3x multiple of long-horizon S&P 500 returns.

**Next:** register the `USLCAP3X` alias in the external `external backtesting application`; then SSO-like 2x large cap and the Treasury-leverage tiers (TMF/UBT/UST/TYD), reusing this build pattern.

## 2026-06-17 - CMDTY Gap Documentation Expanded

Expanded the written gap analysis for the `CMDTY` broad commodities dataset without rebuilding the data.

**Reason for change:** after replacing the 1970-1983 precious-metals-only proxy with the World Bank broad commodity model, the remaining limitations needed to be more explicit in `HANDOVER.md`, methodology, source, validation, and manifest documents. The data are now broad commodities in Segment 0, but they are still not observed daily broad commodity futures total-return history.

**Gaps now documented in detail:**

- Segment 0 is monthly-derived and daily-smoothed, so intra-month daily returns, volatility, drawdowns, and event timing are model artefacts.
- Segment 0 uses the World Bank broad spot-price Total Commodity Index, not a futures excess-return or total-return index; no contract roll yield is present.
- Segment 0 uses World Bank Laspeyres weights based on 2002-04 developing-country export values. This differs materially from DBC, BCOM, and GSCI weighting and eligible futures universes.
- Segment 0 uses Yahoo `^IRX` trading dates and T-bill collateral as project modelling conventions, not as official World Bank index components.
- Segment 1 uses `^SPGSCI` spot returns plus project-modelled collateral, not official S&P GSCI Total Return history.
- Segment 2 treats Yahoo `^BCOM` as excess return and adds project-modelled collateral, but there is no licensed Bloomberg BCOM Total Return daily validation in the repository.
- Segment 3 uses DBC ETF adjusted close, which is an investable net fund return with expenses, tracking, distributions, and Yahoo adjustment dependency.
- The full chain has methodology breaks at the 1984, 1991, and 2006 splices and does not represent one continuous official index family.
- Open, High, Low, and Volume remain blank for model/index segments where the source chain does not provide observed OHLCV.

**Files updated:** `docs/methodology_cmdty.md`, `HANDOVER.md`, `docs/source_registry.md`, `sources/citations/broad_commodities.md`, `docs/validation.md`, `sources/manifests/broad_commodities.yml`, and `PLAN.md`.

## 2026-06-17 - CMDTY Segment 0 Replaced with World Bank Broad Commodity Model

Replaced the `CMDTY` 1970-1983 precious-metals-only fill with a broad commodity model based on the World Bank Commodity Markets Pink Sheet `Total Index`.

**Reason for change:** the prior Segment 0 used only LBMA Gold PM and LBMA Silver. That was correctly flagged as not broad commodities, but it did not satisfy the asset definition for a DBC-like broad commodities dataset.

**New Segment 0 implementation:**

- Active source: World Bank Pink Sheet monthly workbook, `Monthly Indices` worksheet, `Total Index`.
- Source URL: `https://thedocs.worldbank.org/en/doc/5d903e848db1d1b83e0ec8f744e55570-0350012021/related/CMO-Historical-Data-Monthly.xlsx`.
- Coverage: `1970-01-02` to `1984-01-03`, using Yahoo `^IRX` non-missing close dates as the daily trading calendar.
- Daily model: each full month-end `Close` return matches the raw World Bank monthly `Total Index` return; returns are spread across the month with a constant log return.
- `Adj Close` adds Yahoo `^IRX` T-bill collateral using `IRX_close / 100 / 365`.
- Quality flag: `model_world_bank_total_commodity_index_monthly_smoothed_plus_tbill_collateral`.

**Output:** rebuilt `data/processed/broad_commodities.csv` and `.parquet` with 14,159 rows from `1970-01-02` to `2026-06-16`. Segment counts are World Bank broad model = 3,489, SPGSCI = 1,768, BCOM = 3,781, DBC = 5,121. Segment 0 `Close` rises from 100 to about 505.44 by `1984-01-03`; `Adj Close` rises to about 1053.15 with T-bill collateral.

**Validation:** updated the CMDTY tests so Segment 0 full month-end `Close` returns match the raw World Bank monthly `Total Index` returns. The old LBMA basket validation was removed because LBMA gold/silver are no longer active CMDTY sources.

**Caveat:** Segment 0 is now broad commodities, but it is still monthly-derived and daily-smoothed. It is not observed daily futures-index history and does not include futures roll yield. A licensed daily GSCI/BCOM/CRB history or constituent-level futures reconstruction remains the preferred future upgrade.

## 2026-06-17 — CMDTY 1970-1983 Gap Filled with Precious-Metals Proxy

Researched whether the 1970-1983 broad-commodity gap could be filled with public daily data, and implemented a Segment 0 precious-metals proxy fill after confirming no broad-commodity daily data is publicly accessible for this period.

**Sources tested and rejected for the 1970-1983 gap:**

- Yahoo `^CRB`, `^TRJEFFCRB`, `^RJI`, `^CCI`, `TR/CC-CRB` — 404 / empty.
- Yahoo continuous futures (`CL=F`, `GC=F`, `SI=F`, `HG=F`, `NG=F`, agricultural and soft commodities) — HTTP 400 (likely require crumb auth); even where accessible Yahoo continuous futures rarely extend pre-2000.
- FRED CSV endpoints — all timed out (same as prior sessions).
- Stooq.com — bot-protected with JavaScript challenges.
- EIA WTI daily — works but only from 1986 (after the gap).
- World Bank Pink Sheet — 404 / monthly only.
- IMF commodity data — 403.
- BLS API — works but monthly only.
- NBER Macrohistory — HTML reachable but specific data files 404; monthly anyway.
- AQR Commodities for the Long Run (1877+) — page reachable; monthly only.
- Bloomberg BCOM TR, S&P GSCI back-history, Refinitiv, CRSP — all licensed.

**Conclusion:** no public daily broad-commodity index data exists for 1970-1983. Goldman Sachs back-calculated the GSCI to 1970 when launching the index in 1991, but that historical data is not publicly downloadable. LBMA gold and silver are the only daily commodity prices accessible for this period.

**Implementation — Segment 0 precious-metals proxy:**

- Source chain: LBMA Gold PM + LBMA Silver (both daily from 1968), equal-weighted 50/50 daily-rebalanced basket. `Adj Close` adds Yahoo `^IRX` T-bill collateral via the same `IRX%/100/365` formula used in Segments 1 and 2.
- Coverage: 1970-01-02 to 1984-01-03 (last day before SPGSCI return start of 1984-01-04). 3,514 rows.
- Quality flag: `proxy_precious_metals_only_NOT_broad_commodity_lbma_gold_silver_equal_weight_tbill_collateral` — deliberately long and alarming so users cannot miss the warning.
- Source field and Source Notes also carry "PROXY" and "NOT broad commodity" warnings on every row.
- Splice to Segment 1 (SPGSCI): on 1984-01-04, the SPGSCI overlap anchor is 1984-01-03 (= `spgsci_dates[0]`). Same overlap-anchor pattern as the 1991 and 2006 splices.

**Output:** 14,184 rows from 1970-01-02. Segment 0 captures the famous 1970s precious-metals rally — Close rises from 100 (1970-01-02) to a peak of ~2906 in late January 1980 (Hunt Brothers silver squeeze; gold spike during the Iranian Revolution / second oil shock), then collapses to ~900 by 1984-01-03. Adj Close peaks even higher (~4501) due to the high-rate 1970s T-bill collateral compounding.

**Backtest warning documented prominently:** Segment 0 returned ~9x over 1970-1983 while broad commodities returned ~6-7x — backtests treating Segment 0 as broad commodities will overstate returns by 30-50% over the period. The Quality Flag is the explicit filter point. 11 validation tests pass.

## 2026-06-17 — CMDTY Broad Commodities Dataset

Built the `CMDTY` broad diversified commodity futures total-return dataset (`data/processed/broad_commodities.csv`).

**Source chain decisions:**

- **Segment 1 (1984-01-03 to 1991-01-02):** Yahoo `^SPGSCI` (GSCI Spot Index). No public daily broad commodity futures index exists before 1984-01-03; the project's 1970 minimum target cannot be met for this asset class. `^SPGSCI` is a spot-only index — roll yield is missing for this segment, which is a documented methodology gap.
- **Segment 2 (1991-01-03 to 2006-02-06):** Yahoo `^BCOM` (Bloomberg Commodity Index). Verified empirically that `^BCOM` is the **Excess Return** variant (spot + roll yield) by computing the 2021 annual return (27.06%), which matches the known BCOM ER 2021 return (~27.1%). The BCOM Spot Return 2021 was ~25.5% and did not match. T-bill collateral added to `Adj Close` using Yahoo `^IRX` rate (actual/365 convention).
- **Segment 3 (2006-02-07 to present):** Yahoo `DBC` adjusted close. Confirmed `adj close ≠ close` (adj[0]=19.19 vs close[0]=24.20), verifying Yahoo adj close captures accumulated T-bill collateral distributions. No separate collateral model needed.
- **Splice logic:** both boundaries use the "overlap anchor" pattern: the incoming source has a value on the outgoing source's last date, so the first return in the new segment is computed using the new source's own ratio.

**Collateral model (Segments 1 and 2):** `adj_close[t] = adj_close[t-1] × (1 + excess_return[t]) × (1 + IRX_close / 100 / 365)`. This matches the GSCI Total Return definition (actual/365). IRX missing values are forward-filled.

**Output:** 10,671 rows from 1984-01-03. SPGSCI=1,769 rows, BCOM=3,781 rows, DBC=5,121 rows. At the 1991 splice: `Close`≈99.7, `Adj Close`≈141.9 (T-bill collateral roughly doubled the excess-return level over 1984-1991 when rates averaged ~6-8%). Final levels: `Close`≈196.1, `Adj Close`≈522.9.

**Why sources not used:** Yahoo `^SPGSCITR` and `^BCOMTR` return only 1 row of data (no usable history). DJP (BCOM TR ETN) has `adj close == close` due to the ETN structure — total return cannot be extracted. FRED DTB3/TB3MS timed out. Bloomberg BCOM Total Return and S&P GSCI Total Return are the ideal validation sources but require licensed access.

## 2026-06-16

- Created the initial documentation and validation scaffold for a long-horizon daily asset dataset project.
- Set the first dataset target as U.S. large-cap equities, represented by the S&P 500 or closest defensible equivalent.
- Established `1970-01-01` as the minimum required start date for core datasets, with earlier history included only when source quality and methodology support it.
- Chose a Yahoo-compatible output contract so existing Python backtest scripts can switch with minimal adapter work.
- Documented that final datasets should be exported as both CSV and Parquet and should load naturally into pandas.
- Captured initial source findings:
  - S&P Dow Jones Indices describes the S&P 500 as a large-cap U.S. equity gauge covering about 80% of available market capitalization.
  - FRED `SP500` is daily close, index-level data sourced from S&P Dow Jones Indices. FRED notes it is a price index and not a total return index, and that FRED currently includes 10 years of daily history for S&P and Dow Jones series.
  - yfinance provides a Python interface for Yahoo Finance-style data, but states it is not affiliated with, endorsed by, or vetted by Yahoo. Yahoo terms of use must be reviewed before storing or redistributing downloaded data.
  - Direct access to Robert Shiller's Yale data page failed during initial research with a `502 Bad Gateway`; treat Shiller data as a candidate requiring direct verification before use.
- Added initial validation expectations for schema compatibility, minimum coverage, return arithmetic, independent-source comparison, and anomaly detection.

## 2026-06-16 - U.S. Large-Cap Dataset Implementation

- Added explicit per-dataset milestones to `PLAN.md`, with statuses marked as complete, in progress, not completed, or blocked.
- Added `src/build_us_large_cap_sp500.py` to fetch Yahoo Finance chart data for `^GSPC` and export a Yahoo-compatible S&P 500 price-index dataset.
- Built `data/processed/us_large_cap_sp500.csv` and `data/interim/us_large_cap_sp500.csv`.
- Stored the raw Yahoo chart payload under `sources/raw/us_large_cap_sp500_yahoo_chart.json`.
- Wrote build metadata to `sources/manifests/us_large_cap_sp500_build.json`.
- The generated dataset has 14,234 rows, starts on `1970-01-02`, and ends on `2026-06-15`. `1970-01-02` is accepted as the first trading observation after the `1970-01-01` coverage anchor.
- `Adj Close` is retained for Yahoo compatibility, but `Total Return` is intentionally blank because `^GSPC` is a price index and not a dividend-reinvested total-return index.
- Added `tests/fixtures/fred_sp500_sample.csv` from recent FRED `SP500` page values and validated the generated Yahoo close values against it with a `0.01` index-point tolerance.
- Added `requirements.txt` with `requests`, `pandas`, `pyarrow`, and `pytest`.
- Added `src/update_us_large_cap_sp500.py` for incremental updates. It refetches a configurable overlap window from Yahoo chart data, replaces overlapping dates, de-duplicates by date, recomputes price returns, and rewrites CSV/Parquet outputs.
- Installed pandas and pyarrow after increasing the install timeout.
- Ran the incremental update script for end date `2026-06-16`. It refetched 7 overlap rows from `2026-06-05` through `2026-06-16`, kept the final dataset at 14,234 rows, and wrote both CSV and Parquet outputs.

## 2026-06-16 - External Script Integration Test

- Created `the external backtesting application` as a copy of `an earlier external backtesting application`.
- Added a custom ticker alias, `USLCAP`, that loads `data/processed/us_large_cap_sp500.csv` instead of calling yfinance.
- Configured the default test in `external backtesting application` as `USLCAP` versus `SPY`, starting `1993-01-29` so both series have overlapping history.
- Verified the custom loader reads 8,401 rows from `1993-01-29` through `2026-06-15`.
- Ran `external backtesting application` headlessly with the local virtual environment and `MPLBACKEND=Agg`; the script completed successfully.
- Updated `external backtesting application` after `USLCAP` gained full adjusted/total-return data so the custom ticker now loads `Adj Close` instead of `Close`.
- Reran `external backtesting application` headlessly. The custom adjusted `USLCAP` series starts on `1990-01-02` for the configured test window, while `SPY` starts on `1993-01-29`; the script aligns to the overlapping period and completes successfully.

## 2026-06-16 - Daily Adjusted USLCAP Series

- Rejected monthly dividend/interpolation approaches for `USLCAP` because the adjusted series must be daily and must not be estimated from monthly data.
- Added Kenneth French Data Library / CRSP `Portfolios_Formed_on_ME_daily_CSV.zip` as the daily U.S. large-cap/blend total-return source before Yahoo `^SP500TR` can supply daily return changes.
- Kept Yahoo `^GSPC` as the S&P 500 price-index OHLCV source for `Close`.
- Kept Yahoo `^SP500TR` as the daily S&P 500 total-return source after the first date where consecutive `^SP500TR` values allow daily total-return calculation.
- Rebuilt `data/processed/us_large_cap_sp500.csv` and `.parquet` so `Adj Close` is populated from `1970-01-02` onward. `Total Return` is blank only on the first row.
- Added Portfolio Visualizer's FAQ market-data section as a candidate reference for future asset-class source selection: https://www.portfoliovisualizer.com/faq#marketData
- Added Bogleheads Simba's backtesting spreadsheet as an unverified candidate reference for future asset-class source selection: https://www.bogleheads.org/wiki/Simba%27s_backtesting_spreadsheet. Direct fetch returned `403 Forbidden`; treat it as a reference pointer, not a daily raw source.
- Removed the unused Shiller monthly workbook from `sources/raw` to avoid implying that monthly data was used for the daily adjusted series.

## 2026-06-16 - Pre-1990 Validation Checks

- Checked `USLCAP.Total Return` against the raw Kenneth French / CRSP `Hi 30` daily return source for 4,548 rows between 1970 and 1987. Maximum absolute difference was approximately `6.94e-18`.
- Compared annual compounded `USLCAP.Adj Close` returns for 1970-1987 against an external S&P 500 annual total-return reference table. Mean absolute difference was 1.57 percentage points; maximum absolute difference was 4.79 percentage points in 1975.
- Added `docs/us_large_cap_validation_checks.md` and `tests/fixtures/us_large_cap_annual_check_1970_1987.csv`.
- Added repeatable pytest checks for the pre-`^SP500TR` daily source match and annual sanity-check bounds.

## 2026-06-16 - Plan Cleanup and Gold Milestones

- Updated `PLAN.md` with the project workflow used to complete the U.S. large-cap dataset: search for sources, choose methodology, implement, test, and document.
- Marked the U.S. large-cap dataset status as complete and added the pre-1990 validation milestone.
- Added planned milestones for the next dataset, Gold, without starting implementation.

## 2026-06-16 - Gold Dataset Implementation

- Selected LBMA Gold Price PM as the primary daily Gold source after confirming the public JSON endpoint is reachable and starts before 1970.
- Defined Gold as spot/fixing price return in USD per troy ounce. `Close` and `Adj Close` are equal; `Price Return` and `Total Return` are equal.
- Documented that this Gold dataset is not a futures total-return index and not an ETF return series. It excludes storage, insurance, financing, taxes, transaction costs, ETF fees, and futures collateral yield.
- Added `src/build_gold.py`, `src/update_gold.py`, `sources/manifests/gold.yml`, `sources/citations/gold.md`, and `tests/validation/test_gold_contract.py`.
- Built `data/processed/gold.csv` and `data/processed/gold.parquet`.
- Stored raw LBMA PM data under `sources/raw/gold_lbma_gold_pm.json`.
- The generated Gold dataset has 14,175 rows, starts on `1970-01-02`, and ends on `2026-06-15`.
- Ran `src/update_gold.py` for end date `2026-06-16`; it refetched 11 overlap rows from `2026-06-01` through `2026-06-16`, kept the final dataset at 14,175 rows, and wrote both CSV and Parquet outputs.
- Validation passes for schema, coverage, return arithmetic, positive levels, `Adj Close == Close`, and exact raw LBMA PM source matching. Independent daily validation remains an open Gold milestone.
- Updated `the external backtesting application` with the local custom ticker alias `GOLDPM` for `data/processed/gold.csv`. The alias avoids using `GOLD`, which may collide with a traded ticker, and leaves `GLD` available for Yahoo Finance ETF data.

## 2026-06-16 - Dataset Methodology Documentation

- Added `docs/dataset_methodologies.md` as the canonical per-dataset methodology file.
- Documented the `USLCAP` derivation, including asset definition, sources, source-chain method, update method, tests, independent checks, and caveats.
- Documented the `GOLDPM` derivation, including LBMA PM source use, Yahoo-compatible column meanings, update method, tests, GLD comparison findings, and caveats.
- Updated `PLAN.md` so every dataset must include a dedicated methodology entry before it can be treated as complete.

## 2026-06-16 - Long-Term U.S. Treasury Dataset Start

- Added milestones for a TLT-like long-term U.S. Treasury dataset with target alias `LTT`.
- Defined the target as long-duration nominal U.S. Treasury exposure, approximately 20+ years remaining maturity, with coupon/distribution reinvestment reflected in total returns.
- Identified TLT/iShares as the target definition and post-2002 public ETF validation source.
- Built a provisional public-source dataset from Yahoo chart data: VUSTX adjusted returns from 1986-05-19 and TLT adjusted returns from 2002-07-31 onward.
- Added `src/build_long_term_us_treasury.py`, `src/update_long_term_us_treasury.py`, `sources/manifests/long_term_us_treasury.yml`, `sources/citations/long_term_us_treasury.md`, and `tests/validation/test_long_term_us_treasury_contract.py`.
- Documented that the complete 1970+ dataset should be built from CRSP/WRDS daily Treasury issue-level data by selecting nominal Treasury bonds with at least 20 years remaining maturity and computing coupon-aware daily holding-period returns.
- Documented FRED DGS30 as a candidate par-bond model input for part of the pre-VUSTX period, but not a sufficient observed total-return source. FRED CSV retrieval timed out in this environment.
- Extended the long-term Treasury dataset to `1970-01-02` using the Federal Reserve nominal yield curve CSV. The pre-VUSTX segment is a synthetic 25-year constant-maturity par Treasury model with coupon carry included in `Total Return`.
- Rebuilt `data/processed/long_term_us_treasury.csv` and `.parquet`; the dataset now has 14,174 rows from `1970-01-02` through `2026-06-15`.

## 2026-06-16 - Long-Term Treasury Total-Return Fix

- Investigated a flat-looking LTT total-return level in the 1970-1986 Fed model segment.
- Found that `build_fed_synthetic_rows()` emitted one-day relative price and total-return levels around 100, so the downstream normalizer recomputed returns from daily relative values rather than from a cumulative level series.
- Fixed the Fed synthetic segment to compound cumulative `Close` and `Adj Close` levels before splicing into VUSTX and TLT.
- Rebuilt `data/processed/long_term_us_treasury.csv` and `.parquet`. The Fed-model `Adj Close` now compounds from 100.0 on `1970-01-02` to approximately 194.33 on `1986-05-19`.
- Added a regression test requiring the Fed-model segment to show cumulative total-return growth rather than remaining flat around 100.

## 2026-06-16 - Intermediate-Term U.S. Treasury Dataset

- Added ITT dataset: IEF-like 7-10 year nominal U.S. Treasury total-return series, targeting `1970-01-01` minimum coverage with coupon reinvestment in `Adj Close` and `Total Return`.
- Defined target definition: intermediate-duration nominal U.S. Treasuries with approximately 7-10 years remaining maturity, represented by IEF. Backtest alias: `ITT`.
- Source chain chosen:
  - Federal Reserve nominal yield curve model (1970-01-02 to 1991-10-28): synthetic 8.5-year constant-maturity par Treasury, evaluated at the midpoint of the 7-10 year IEF target band. `Total Return` includes daily coupon carry.
  - Yahoo VFITX adjusted returns (1991-10-29 to 2002-07-30): Vanguard Intermediate-Term Treasury Fund as a public fund proxy before IEF has daily return history.
  - Yahoo IEF adjusted returns (2002-07-31 onward): iShares 7-10 Year Treasury Bond ETF.
- Built `data/processed/intermediate_term_us_treasury.csv` (14,158 rows, 1970-01-02 to 2026-06-15) and `data/processed/intermediate_term_us_treasury.parquet`.
- Added `src/build_intermediate_term_us_treasury.py` and `src/update_intermediate_term_us_treasury.py`.
- Added `sources/manifests/intermediate_term_us_treasury.yml` and `sources/citations/intermediate_term_us_treasury.md`.
- Added `tests/validation/test_intermediate_term_us_treasury_contract.py`; all 7 new tests pass alongside the existing 25, total 32 passing.
- Updated `PLAN.md` (ITT milestones marked complete), `docs/dataset_methodologies.md` (full ITT methodology entry), `docs/source_registry.md` (IEF, VFITX, Fed curve, and CRSP entries for ITT), `docs/validation.md` (ITT independent-source check requirements), and `HANDOVER.md`.

## 2026-06-16 - Documentation Restructure

- Split `docs/dataset_methodologies.md` into four per-dataset methodology files: `docs/methodology_uslcap.md`, `docs/methodology_goldpm.md`, `docs/methodology_itt.md`, `docs/methodology_ltt.md`.
- `docs/dataset_methodologies.md` is now a slim index table linking to each file, plus the methodology template.
- Cleaned up `docs/methodology.md`: removed duplicated USLCAP and Gold dataset sections (now in individual files); retained the general project methodology (canonical shape, return calculations, source boundaries, incremental update rules, minimum coverage, quality flag conventions).
- Updated `PLAN.md` to reference `docs/methodology_<alias>.md` naming convention and revised the documentation step in the build workflow.
- Updated `AGENTS.md` and `CLAUDE.md` (kept identical) to document the new per-dataset file pattern.

## 2026-06-16 - Short-Term U.S. Treasury Dataset

- Added STT dataset: SHY-like 1-3 year nominal U.S. Treasury total-return series, targeting `1970-01-01` minimum coverage with coupon reinvestment in `Adj Close` and `Total Return`.
- Defined target definition: short-duration nominal U.S. Treasuries with approximately 1-3 years remaining maturity, represented by SHY. Backtest alias: `STT`.
- Source chain:
  - Federal Reserve nominal yield curve model (1970-01-02 to 1991-10-28): synthetic 2-year constant-maturity par Treasury, evaluated at the midpoint of the 1-3 year SHY target band. `Total Return` includes daily coupon carry.
  - Yahoo VFISX adjusted returns (1991-10-29 to 2002-07-30): Vanguard Short-Term Treasury Fund as a public fund proxy before SHY has daily return history.
  - Yahoo SHY adjusted returns (2002-07-31 onward): iShares 1-3 Year Treasury Bond ETF.
- The Fed model segment compounded from 100 to approximately 1142 by late 1991, reflecting the high short-rate environment of the 1970s–80s. The large gap between `Close` and `Adj Close` for this period is expected and correct: coupon income dominates total return for short-duration bonds.
- Built `data/processed/short_term_us_treasury.csv` (14,158 rows, 1970-01-02 to 2026-06-15) and `data/processed/short_term_us_treasury.parquet`.
- Added `src/build_short_term_us_treasury.py` and `src/update_short_term_us_treasury.py`.
- Added `sources/manifests/short_term_us_treasury.yml` and `sources/citations/short_term_us_treasury.md`.
- Added `tests/validation/test_short_term_us_treasury_contract.py`; all 7 new tests pass alongside the existing 32, total 39 passing.
- Updated `PLAN.md`, `docs/dataset_methodologies.md`, `docs/methodology_stt.md`, `docs/source_registry.md`, `docs/validation.md`, `HANDOVER.md`, and `LOG.md`.

## 2026-06-16 - LTT Yield Instability Fix

- Identified that the LTT dataset had a spurious ~38% peak-to-trough intra-year drawdown in 1970.
- Root cause: `build_fed_synthetic_rows` was evaluating the Svensson fitted yield at 25-year maturity using raw BETA parameters. The BETA0 parameter (the long-run asymptote) is numerically ill-conditioned in the early 1970s — it jumps by hundreds of basis points on consecutive days. The Federal Reserve's pre-computed `SVENY25` column is `NaN` before November 1985, which is the Fed's own indicator that this extrapolation is unreliable.
- Fix: replaced the raw Svensson 25-year extrapolation with a stable yield hierarchy:
  1. Fed `SVENY25` / `SVENY30` pre-computed smooth yields (Nov 1985 to VUSTX start, already working).
  2. Yahoo `^TYX` observed 30-year Treasury yield (1977-02-15 to Nov 1985); fetched alongside other Yahoo sources in the build.
  3. Fed `SVENY10` as a proxy (Aug 1971 to Feb 1977); the yield curve was flat/inverted in this period so 10y ≈ 25y within ~50 bps.
  4. Svensson-fitted 10-year yield from BETA parameters (1970 to Aug 1971); the Svensson fit is stable at 10 years.
- Also fixed a secondary bug: the previous-day bond price was hardcoded as 100, but a par bond in the continuous-compounding framework prices at ~98.5, not 100. Dividing by 100 (instead of the actual previous price) compounded a ~1.5% daily loss, collapsing Adj Close to near 0. Reverted to explicit `previous_price` computation.
- Rebuilt `data/processed/long_term_us_treasury.csv` and `.parquet`. Worst intra-1970 drawdown is now -13.67% (down from spurious -38%). Annual returns are plausible: +17% in 1970 (rates fell in recession), -34% worst drawdown in Sep 1981 (Volcker peak), +45% in 1982 (Volcker pivot), +25-29% in 1985-86.
- STT confirmed: the `external backtesting application` alias was a typo (`"sTT"` instead of `"STT"`); fixed separately.
- Updated `docs/methodology_ltt.md` and `docs/source_registry.md` to document the yield hierarchy and the instability of Svensson extrapolation at 25+ years in the early 1970s.
- All 39 validation tests pass.

## 2026-06-16 - GitHub Repository Link Preparation

- Renamed the planned project folder label from `datasets` to `financial_datasets` to match the GitHub repository name.
- Added `.gitignore` entries for Python bytecode, pytest cache, and local virtual environments before initializing Git.

## 2026-06-19 - CPI Inflation Deflator and Real-Return Analysis

- Added `CPI` / `cpi_inflation`: a calendar-daily U.S. CPI-U deflator from official BLS `CUSR0000SA0` monthly CPI data.
- Used BLS as the active source after direct FRED `CPIAUCSL` CSV retrieval timed out. FRED remains documented as a validation/reference source for the same CPI-U concept.
- Built `data/processed/cpi_inflation.csv` and `.parquet` with 20,624 rows from `1970-01-01` through `2026-06-19`; latest monthly CPI observation is `2026-05-01`.
- Daily rows between monthly observations use constant log interpolation and are flagged `model_daily_log_interpolated_monthly_cpi_u`. Rows after the latest monthly release are flagged `carried_forward_latest_monthly_cpi_u_level`.
- Added `src/build_cpi_inflation.py`, `src/update_cpi_inflation.py`, manifest, citation notes, methodology, and validation tests.
- Copied `an earlier external backtesting application` to `external backtesting application` and changed inflation adjustment to use the local CPI dataset only for fully local custom-dataset runs. If either the portfolio or comparison uses yfinance API tickers, `external backtesting application` keeps the previous live FRED CPI fetch path so current Yahoo prices are not deflated with a stale local CPI CSV.

## 2026-06-19 - Global All-World Stock Proxy

- Added `GLSTOCK` / `global_stocks`, a long-horizon global all-world equity total-return proxy.
- Source chain: USLCAP daily path scaled to public MSCI World gross annual returns for 1970-1989, USLCAP gap fill through 1990-06-29, Kenneth French Developed 3 Factors daily total return (`Mkt-RF + RF`) from 1990-07-02 through VT inception, then observed Yahoo VT adjusted-close returns.
- Built `data/processed/global_stocks.csv` and `.parquet` with 14,396 rows from `1970-01-02` through `2026-06-18`.
- Added `src/build_global_stocks.py`, `src/update_global_stocks.py`, manifest, citation notes, methodology, and validation tests.
- Documented the key caveat: this is a public-source model-derived proxy, not licensed observed daily MSCI ACWI or FTSE All-World history. Emerging markets enter only in the VT segment.
- Added `GLSTOCK` to `external backtesting application`.

## 2026-06-19 - Unhedged Global Bond Proxy

- Added `GLBOND` / `global_bonds`, an unhedged global bond total-return proxy in USD.
- Rejected the first draft's early ITT-only segment because it was U.S.-only and not sufficiently global.
- Rebuilt the early segment from the JST Macrohistory Database: annual country-level government bond total returns converted to USD with exchange rates and weighted by prior-year USD GDP across advanced economies.
- Expanded the annual JST basket to daily rows by constant log return and clearly flagged it as annual-smoothed model data.
- Added an observed daily segment from a 45% BND / 55% BWX adjusted-close blend. BWX supplies unhedged international local-currency bond exposure.
- Built `data/processed/global_bonds.csv` and `.parquet` with 14,236 rows from `1970-01-02` through `2026-06-18`.
- Added `src/build_global_bonds.py`, `src/update_global_bonds.py`, manifest, citation notes, methodology, and validation tests.
- Added `GLBOND` to `external backtesting application`.

## 2026-06-19 - GLBOND de-smoothing of the 1970-2007 segment

- Problem: the original early segment spread one JST annual basket return across every trading day with a constant daily log return. All intra-year volatility, drawdowns, and crisis timing before 2007 were therefore artificial.
- Replaced the flat annual ramp with a reconstructed daily path while keeping JST as the exact annual anchor (the "realistic shape + annual anchor" pattern used by GLSTOCK).
- Sources added (both via DBnomics, key-less): BIS `WS_XRU` daily exchange rates (local currency per USD, all 16 countries, back to 1969-12/1971; euro-legacy via chained `.EUR.`) for a genuine daily FX leg; OECD MEI `IRLTLT01` monthly 10-year government-bond yields for a monthly rate leg (constant-maturity 10y par-bond reprice + coupon carry, smoothed within month).
- Verified FRED `fredgraph.csv` and stooq daily-FX CSV are blocked in this environment; documented as `blocked` and used BIS via DBnomics instead.
- Method: per country, `(1 + daily_bond) * (1 + daily_fx) - 1`, GDP-weighted into a basket (prior-year USD GDP weights from JST), then a per-year multiplicative overlay forces each calendar year to compound exactly to the JST annual basket. Countries lacking an early yield (Japan pre-1989, Italy pre-1991, Spain/Nordics) are basket-proxied on the rate leg but still carry daily FX.
- Decisions confirmed with the user: keep JST as the hard annual anchor; build the most faithful daily option (daily BIS FX + per-country monthly OECD/MEI yields).
- Results: early-segment annualized vol ~8.2% (was ~0 within-year), realistic by decade (5.5% 1970s, 9.5% 1980s); >=247 distinct daily returns per year (was 1); per-year JST anchor invariant holds to ~1.7e-9; correctly-timed FX events (best day +5.1% on 1985-09-23 after the Plaza Accord, worst day -4.85% on 1978-11-02 around the Carter dollar-rescue rally).
- Quality flag renamed to `model_jst_anchored_daily_fx_monthly_yield_global_govt_bond_unhedged`. Row count unchanged (14,236); observed BND/BWX segment unchanged.
- Updated build script, validation tests (added de-smoothing regressions: distinct daily returns, realistic vol band, FX-event directions), methodology, source registry, validation docs, manifest, citations, PLAN, and HANDOVER. Full validation suite: 122 passed.

## 2026-06-19 - GLBOND GDP-weighting bug fix + Option B feasibility study

- Feasibility study (Option B: make the rate leg daily): genuinely daily 10y sovereign yields reachable that cover our window are US (in-repo Fed model, 1970), Japan (MoF `jgbcm_all.csv` at .../data/, daily 1974-09-24+, cp932 + Japanese-era dates), and UK (BoE GLC nominal daily curve `.zip`, ~39MB, from 1979). Bank of Canada daily only from 2001; Bundesbank clean API only from 1997 (BBIB1 is monthly bank rates, not bond yields; legacy WT codes 404); RBA blocked (403); France/Italy/Netherlands/etc. no free daily back this far. DBnomics does NOT mirror these daily yields (BOC/BOJ expose only macro aggregates), so Option B needs bespoke per-source parsers. With correct weights, US+JP+UK daily ~= 62% of the basket from 1979 (~56% from 1974); Germany cannot extend coverage before 1997. Verdict: Option B partially feasible, second-order (FX already daily); decision deferred.
- Bug found during the study: the basket GDP weighting used JST nominal `gdp` / `xrusd`, but JST `gdp` has inconsistent local-currency units across countries (US in billions of USD = 7,639.7; Spain in millions of pesetas = 76,635,394). So `gdp/xrusd` mixed billions and millions and mis-weighted the basket toward small economies: 1995 weights were ESP 21.8%, NLD 16.2%, AUS 14.7% with the US at ~0.3%. This skewed the committed annual anchor (the circular annual test never caught it).
- Fix: weight by comparable real GDP (`rgdpmad` real GDP per capita in 1990 international dollars x `pop`). Corrected 1995 weights: US 42.1%, JP 16.0%, DE 9.1%, FR 7.0%, GB 6.5%, IT 6.3%; G4 ~71-74%, US always largest. The annual basket anchor moved 6-10pp in many years (e.g. 1985 +25.65% -> +35.62%, 1990 +21.93% -> +12.43%).
- Rebuilt GLBOND (14,236 rows, unchanged shape): overlay invariant still ~1.4e-9; early-segment annualized vol now ~5.0% (down from ~8.2% because the US, ~42% weight, carries no FX vol); FX events still correctly signed (+3.35% Plaza, -3.28% dollar-rescue). Added a weight-sanity regression test (US largest, G4 > 50%). Updated build script, tests, methodology, source registry, manifest, citations, PLAN, HANDOVER. Full validation suite: 123 passed.

## 2026-06-19 - GLBOND Option B: daily rate leg for US / Japan / UK

- Implemented the partial daily rate leg agreed after the feasibility study: replaced the flat within-month rate distribution with genuine daily bond total returns for the three largest weights, keeping all other countries (and US/JP/UK before their daily-yield start) on the OECD monthly leg. Daily FX and the JST annual anchor are unchanged.
- US: in-repo `intermediate_term_us_treasury.csv` daily 7-10y Treasury total return (1970+). Japan: MoF `jgbcm_all.csv` daily 10y JGB yield, continuous from 1986-07-05 (cp932, Japanese-era dates), repriced daily as a 10y par bond + carry. UK: BoE GLC nominal daily yield curve zip, "4. nominal spot curve" sheet, 10y spot from 1979, parsed manually (no openpyxl dependency). New helper `daily_bond_returns_from_yields` forward-fills national yields onto the trading grid and reprices day-to-day.
- Germany probed as a fourth leg but free daily yields reach only 1997 (Bundesbank clean API; legacy WT codes 404; DBnomics BUBA/BBIB1 is monthly bank rates), so Germany stays monthly. Bank of Canada daily 10y only from 2001; RBA blocked. DBnomics does not mirror these daily yields, so each is a bespoke fetch/parser.
- Daily rate coverage: US 1970-01-05..2007 (9,457 days), Japan 1986-07-08..2007 (5,364), UK 1979-01-03..2007 (7,262) -> ≈62% of the basket on a daily rate leg from 1979. Build metadata now records `daily_rate_coverage`.
- Raw provenance: MoF CSV (~1.2 MB) cached whole; the BoE 39 MB archive is fetched at build time but NOT committed - only the compact extracted 10y series `global_bonds_boe_gilt_10y.csv` (~140 KB) is persisted.
- Results: overlay invariant still ~1.2e-9; early-segment vol rose to ~5.9% (from ~5.0%) with sensible time structure (3.7% in 1970-78 with only the US daily, 7.7% 1979-85 once the UK joins); US Treasury event days (e.g. 1987-10-20, 1994 selloff) now propagate to the basket where monthly smoothing had buried them. FX events still correctly signed.
- Added a `daily_rate_leg_coverage` regression test (US from 1970, JP from 1986, UK from 1979). Updated build script, tests, methodology, source registry, validation docs, manifest, citations, PLAN, HANDOVER. Full validation suite: 124 passed.

## 2026-06-20 - GOLDPM redefined to track GLD; GOLD2X holiday double-count fixed

**Why:** The user reported that the synthetic gold series diverges materially from the ETFs it is meant to stand in for (GLD/UGL) — by >1% CAGR — and asked the synthetic datasets to track the real funds, *including fees/drag*, back to 1970.

**Diagnosis (empirical, against live Yahoo GLD/UGL over the overlap):**

- **1x:** old pure-spot `GOLDPM` outran `GLD` by **0.50%/yr** (2004-2026). Decomposed: ~0.40% is GLD's expense ratio (a real cost — GLD *should* lag spot), the rest zero-mean LBMA-PM-fix-vs-4pm-close timing noise (daily corr 0.65, but cumulative-neutral). The ">1%" the user saw is endpoint sensitivity: the cumulative GOLDPM/GLD ratio wanders in a ~18% band because the two are struck ~6h apart, so a finite window ending on a volatile day (2026-06-15: +4.0% PM vs +2.6% GLD) overstates the gap.
- **2x:** `GOLD2X` overshot `UGL` by **+33.8% cumulatively / +1.89%/yr** — even though it splices observed UGL after 2008. Traced to a **holiday double-count bug**: 98 synthetic fills on LBMA-open/US-closed holidays compounded an extra 2x-gold day, while UGL's reopen return already spanned the holiday. Zeroing those 98 days' compounding collapses GOLD2X/UGL to exactly 1.000; they explained 88% of the log drift (concentrated in the 2009-2012 bull run).

**What changed:**

- **`GOLDPM` redefined to track GLD with costs.** `Close` stays pure LBMA PM spot (so `Price Return` is pure spot); `Adj Close` is now a GLD-tracking total-return index: spot minus GLD's 0.40% expense drag (actual/365) before GLD's 2004-11-18 inception, then **observed GLD adjusted-close returns** (Adj Close exactly proportional to GLD). `Adj Close != Close` now (carries the fee). US-holiday rows (GLD not trading) held flat to avoid the same double-count. Verified: observed-era CAGR gap vs GLD 0.0000%, constant level ratio; full-history implied fee drag 0.411%/yr.
- **`GOLD2X` holiday bug fixed + re-based.** Post-inception US-holidays are now held flat (`observed_ugl_us_holiday_flat`, Total Return 0) instead of synthetic-filled; observed-era `Adj Close` is now an exact constant multiple of UGL (CAGR gap 0.0000%). Also switched the 2x underlying from GOLDPM `Total Return` to GOLDPM `Price Return` (pure spot) so GLD's fee isn't double-counted in the leveraged model.
- **Datasets rebuilt:** both 14,179 rows, 1970-01-02 → 2026-06-19. `gold`: model 8,772 / observed GLD 5,287 / US-holiday flat 120. `gold_2x`: synthetic 9,786 (all pre-inception) / observed UGL 4,295 / US-holiday flat 98.
- **Source availability:** a US-close gold base (COMEX futures) would lift daily GLD correlation from ~0.65 to ~0.89 but Stooq is blocked here and Yahoo `GC=F` only reaches 2000; deferred as a daily-fidelity upgrade (timing basis is cumulative-neutral). Recorded in source registry.

**Tests:** rewrote `test_gold_contract.py` (drops Adj==Close; adds fee-model and exact-GLD-tracking segment tests) and updated `test_gold_2x_contract.py` (no synthetic fills in observed era, holiday rows flat, Price-Return base, and a new `test_observed_dataset_tracks_ugl_cumulatively` regression guard for the double-count). Updated methodology (goldpm/gold2x), source registry, validation, manifests, citations, dataset index, PLAN, HANDOVER. Full validation suite: **128 passed**.

**Note:** the backtester aliases are unchanged — `GOLDPM`/`GOLDPM2x` still point at the same CSVs, now cost-inclusive, so `external backtesting application` needs no edit.

## 2026-06-20 - GOLDPM/GOLD2X calendar fix (observed era moved to the NYSE calendar)

**Why:** After the redefinition above, the user re-ran `external backtesting application` and still saw a *very large* GOLDPM-vs-GLD deviation since 2004. The dataset levels were perfectly proportional to GLD (verified), so this was not stale data.

**Diagnosis:** A **trading-calendar mismatch**. GOLDPM was on the London/LBMA calendar; GLD is on the US/NYSE calendar. `external backtesting application` compares series by *intersecting their daily-return dates and compounding* (lines 704-709). On the ~141 days in 2004-2026 where GLD trades but LBMA is closed (UK bank holidays — Easter Monday, early May, August bank holiday, Boxing Day, …), GLD's return is dropped from the intersection while GOLDPM folds the move into a spanning return. Reproducing the script's exact logic gave GOLDPM **10.51%/yr vs GLD 8.55%/yr — +1.96%/yr, +47% cumulative** (final ratio 1.4719) from 112 mismatched days, even though the levels matched. GOLD2X vs UGL had the same disease (GOLD2X iterates GOLDPM's dates).

**Fix:** Build the **observed era on GLD's (NYSE) trading calendar** instead of the LBMA calendar. One row per GLD trading day, `Adj Close = scale · GLD_adj`, so the dataset aligns with GLD day-for-day and the script's date intersection keeps every GLD day. This drops the LBMA-open/US-closed flat rows (GLD doesn't trade then) and *adds* the UK-bank-holiday rows GLD does trade. On those ~141 UK-bank-holiday days there is no LBMA fix, so `Close` is **stepped by GLD's move** (flag `observed_gld_us_open_lbma_holiday_close_gld_step`) — more realistic than a flat carry-forward, and it telescopes back to the next LBMA fix so `Close` stays LBMA-anchored and `Price Return` stays clean. The pre-2004 model era stays on the LBMA calendar. GOLD2X inherits the fix automatically (it iterates GOLDPM's dates): its observed era is now on the NYSE calendar, the holiday-flat path is unused (0 rows), and it reproduces UGL exactly.

**Verification (reproducing the script's intersect-and-compound):** GOLDPM vs GLD **gap 0.000%, final ratio 1.0000**; GOLD2X vs UGL **gap 0.000%, ratio 1.0000**. Both deviations eliminated.

**Rebuilt:** both 14,200 rows, 1970-01-02 → 2026-06-18. `gold`: model 8,771 / observed GLD 5,288 (incl. 141 UK-holiday GLD-step-close rows). `gold_2x`: synthetic 9,789 / observed UGL 4,411 / holiday-flat 0.

**Tests:** updated `test_gold_contract.py` (observed dates must equal GLD's trading days; Close matches raw LBMA on fix rows, GLD-step rows excluded; ffill→GLD-step flag) and `test_gold_2x_contract.py` (holiday-flat lower bound removed; **calibration test rewritten to recompute the spread on clean raw LBMA-calendar spot returns** — the basis the spread was calibrated on — because the continuous model on the now-NYSE Price Return is calendar-inflated; the shipped series is still checked exactly against UGL). Updated methodology, manifests, citations, validation. Full validation suite: **128 passed**.

**Note:** still no backtester edit needed — same aliases/CSVs. The script's "intersect daily returns" comparison is now safe for gold because the dataset shares GLD/UGL's calendar; the deeper script-level fix (compare levels, or reindex onto one calendar before differencing) would also help any future cross-calendar asset.
