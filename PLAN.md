# Daily Asset Dataset Project Plan

## Purpose

This project builds long-horizon daily datasets for individual asset classes so Python backtests can run over longer periods than are usually available from live ETF, ETN, or fund tickers.

The first dataset is U.S. large-cap equities, represented by the S&P 500 or the closest defensible equivalent. Every core asset dataset must target a minimum start date of `1970-01-01`; earlier history should be included when reliable data exists and the methodology can be documented.

## Public-release privacy plan

The intended public home is `https://github.com/mwilczynska/financial_datasets`. The public identity may expose only the GitHub handle `mwilczynska` and a GitHub-generated noreply commit address.

Do not publish personal email addresses, real-name commit identities, local filesystem paths, private downstream-project names or filenames, personal location, employer, phone number, credentials, or private profile details.

Before changing visibility:

- Preserve the complete private repository, including its current history and uncommitted work, in a separate private archive.
- Review the GitHub account profile and repository-owner settings for unintended public details before changing visibility.
- Publish only a sanitized history whose author and committer metadata use the approved public GitHub identity; do not make the existing private history public.
- Use repository-relative generated metadata paths and run `python src/audit_public_release.py` against the candidate tree and final public history.
- Publish the requested processed and interim datasets with their source-specific caveats; review raw source caches separately and keep them private unless their terms explicitly permit publication.
- Review the exact staged file list and exclude private branches, tags, releases, issue attachments, Actions artifacts, and local tool state.
- Clone the public repository while signed out and repeat the audit after publication.

## Output Contract

Datasets should be compatible with scripts that previously consumed Yahoo Finance or `yfinance` data. The preferred output shape is:

```text
Date, Open, High, Low, Close, Adj Close, Volume
```

Project-specific columns may be added after those fields:

```text
Price Return, Total Return, Source, Quality Flag, Source Notes
```

Rules:

- `Date` is a trading date in ISO format.
- `Close` is the price-return level or best available close-level proxy.
- `Adj Close` is the total-return-adjusted level when it is defensible; otherwise it is the same as `Close` and flagged.
- `Open`, `High`, `Low`, and `Volume` may be blank for reconstructed index-level datasets where no reliable OHLCV source exists.
- CSV and Parquet are both required for final processed datasets.
- Final datasets must load cleanly into pandas with `Date` as a datetime column or index.

## Folder Structure

```text
financial_datasets/
  README.md
  LICENSE
  DATA_LICENSE.md
  SECURITY.md
  PUBLIC_RELEASE.md
  PLAN.md
  AGENTS.md
  CLAUDE.md
  LOG.md
  docs/
    methodology.md
    dataset_methodologies.md
    source_registry.md
    validation.md
  sources/
    raw/
      README.md
    manifests/
      us_large_cap_sp500.yml
    citations/
      us_large_cap_sp500.md
  data/
    interim/
      README.md
    processed/
      README.md
  tests/
    fixtures/
      README.md
    validation/
      README.md
      test_us_large_cap_contract.py
  notebooks/
    README.md
  src/
    README.md
```

## Dataset Methodology

Each dataset must have:

- A dedicated methodology file in `docs/` named `methodology_<alias_lowercase>.md`.
- An entry in `docs/dataset_methodologies.md` (the index).
- A source registry entry with primary, secondary, and validation sources.
- Retrieval metadata: URL or API endpoint, retrieval date, source version when available, and local raw-file path if stored.
- Transformation notes: adjustments, return calculations, joins, interpolation, and source-boundary behavior.
- Quality flags for observed, adjusted, reconstructed, estimated, or incomplete fields.
- Independent-source validation checks before a dataset is treated as backtest-ready.

Each per-dataset methodology file must cover:

- Dataset identifier and backtest ticker alias.
- Asset definition and what `Close`, `Adj Close`, `Price Return`, and `Total Return` represent.
- Output files table: CSV, Parquet, manifest, citation notes, build script, update script, and test file.
- Production sources, validation sources, and rejected or limited sources.
- Step-by-step build method, including source splices, rebasing, quality flags, and assumptions.
- Update method.
- Test coverage and independent check findings.
- Known caveats and what a future upgrade would require.

## Build Workflow

Every new dataset should follow the same working sequence proven by the U.S. large-cap implementation:

1. Search for sources.
   - Start broad with the target asset class, not only the most familiar ticker or ETF.
   - Separate price-index, total-return, spot, futures, and fund/ETF data.
   - Prefer daily sources that cover the `1970-01-01` anchor or earlier.
   - Record candidate, rejected, validation, and active sources in `docs/source_registry.md` and the relevant manifest.
2. Choose a defensible methodology.
   - Define what `Close` and `Adj Close` mean for the asset.
   - Use observed daily data where available.
   - Do not use monthly interpolation or estimated daily returns when the dataset is labelled daily.
   - If multiple daily sources are chained, document the handoff date and quality flags.
3. Implement the pipeline.
   - Add or update a build script under `src/`.
   - Add an incremental update script that refetches an overlap window, stitches by `Date`, recomputes returns, and rewrites CSV/Parquet together.
   - Store raw files and source metadata under `sources/raw/` and `sources/manifests/`.
   - Keep `src/update_all_datasets.py` aligned with the dataset dependency graph so a single command can refresh the complete processed dataset suite.
4. Test the dataset.
   - Validate schema, date coverage, unique sorted dates, positive levels, and return arithmetic.
   - Compare daily rows against the raw active source.
   - Add at least one independent-source check. If only annual/monthly independent data exists, use it as a sanity check and label it as such.
5. Document the result.
   - Update `PLAN.md`, `LOG.md`, `docs/dataset_methodologies.md` (index), `docs/methodology_<alias>.md` (new per-dataset file), `docs/validation.md`, source registry, citations, and tests.
   - Clearly state whether the dataset is official, proxy, reconstructed, or source-chained.
   - Record the complete per-dataset methodology before moving a dataset to `complete`.
   - Keep future-agent instructions in `AGENTS.md` and `CLAUDE.md` identical.

For U.S. large-cap equities:

- Use S&P 500 daily close levels as a price-return benchmark where licensing and coverage allow.
- Treat total return separately from price return.
- Use long-run sources such as Robert Shiller's dataset only for reconstruction or cross-checking unless daily data is directly available and documented.
- Never silently mix observed index data, ETF data, and reconstructed data in one level series without flagging source boundaries.

## Source Principles

- Prefer official sources when they are accessible and licensed for the intended use.
- Use Yahoo-compatible structure for output, but do not assume Yahoo or yfinance data has long enough history for the project goal.
- FRED `SP500` is useful for validation and recent official close levels, but it is price-index only and currently exposes only 10 years of daily history under the FRED/S&P agreement.
- S&P Dow Jones Indices is the authoritative index owner, but redistribution and local storage require attention to licensing terms.
- All source limitations must be copied into `LOG.md` and linked from `docs/source_registry.md`.

## Validation Requirements

Before any processed dataset is used for backtests:

- Coverage must reach `1970-01-01` unless an explicit exception is logged.
- Schema must match the Yahoo-compatible contract.
- Return columns must recompute from the relevant level columns within a documented tolerance.
- Overlapping dates must be checked against at least one independent source.
- Gaps, duplicate dates, non-positive levels, suspicious jumps, and source-boundary discontinuities must be reported.
- Full-suite refreshes should use `python src/update_all_datasets.py`, which delegates to per-dataset update scripts and runs `tests/validation` by default after successful updates.
- Heavy historical inputs for `GLBOND` and `GLSTBOND` are cached for ordinary daily updates; use `--refresh-static-sources` only when intentionally refetching JST/BIS/OECD/MoF/BoE source files.

## Dataset Milestones

### U.S. Large-Cap Equity / S&P 500 Equivalent

Status: `complete`

| Milestone | Status | Notes |
| --- | --- | --- |
| Establish documentation, source registry, citation, and test scaffold | Complete | Root docs, source docs, and initial validation tests exist. |
| Implement a U.S. large-cap equity source manifest | Complete | `sources/manifests/us_large_cap_sp500.yml` exists. |
| Build a normalized Yahoo-compatible `^GSPC` daily price-index CSV | Complete | Generated dataset starts on `1970-01-02`, the first trading observation after the `1970-01-01` anchor. |
| Add independent validation fixtures and tests | Complete | Added a recent FRED `SP500` fixture and validation test with a rounding tolerance. |
| Export final CSV under `data/processed/` | Complete | `data/processed/us_large_cap_sp500.csv` exists. |
| Export final Parquet under `data/processed/` | Complete | `data/processed/us_large_cap_sp500.parquet` exists. |
| Add incremental update/stitching script | Complete | `src/update_us_large_cap_sp500.py` refetches an overlap window, de-duplicates by date, recomputes returns, and rewrites CSV/Parquet. |
| Add daily adjusted/total-return data back to 1970 | Complete | `Adj Close` and `Total Return` are populated from daily Kenneth French/CRSP large-cap returns before `^SP500TR` daily returns are available, then from `^SP500TR`. |
| Add pre-1990 validation checks | Complete | Daily returns match the raw French/CRSP source exactly; annual aggregates are sanity-checked against an external S&P 500 total-return reference. |
| Write per-dataset methodology | Complete | `docs/dataset_methodologies.md` documents sources, derivation method, transformation steps, tests, independent checks, and caveats for `USLCAP`. |

### Gold (GLD-tracking)

Status: `production_built` — tracks SPDR Gold Shares (`GLD`) including fees, extended to 1970.

| Milestone | Status | Notes |
| --- | --- | --- |
| Define asset contract | Complete | `Close` = LBMA Gold Price PM USD/oz (pure spot; `Price Return` is pure spot). `Adj Close` = GLD-tracking total return: spot minus GLD's 0.40% expense drag pre-2004, then observed GLD. `Adj Close != Close` (carries the fee). Redefined 2026-06-20 from the earlier pure-spot definition. |
| Search and classify sources | Complete | LBMA PM (active, Close/Price Return + pre-2004 model) and Yahoo GLD (active, Adj Close from 2004). LBMA AM / FRED Gold PM validation; Nasdaq blocked (403); US-close COMEX base deferred (Stooq blocked, `GC=F` only to 2000). |
| Select daily source chain back to 1970 | Complete | LBMA PM 1970→2004-11-18 (modeled, fee-dragged, LBMA calendar) → observed GLD 2004-11-19→present (on GLD's NYSE calendar so it aligns with GLD day-for-day). Levels compound continuously; UK-bank-holiday rows carry a GLD-stepped Close. |
| Implement source manifest and citations | Complete | Updated `sources/manifests/gold.yml` and `sources/citations/gold.md` for the GLD-tracking definition. |
| Build CSV and Parquet outputs | Complete | `data/processed/gold.csv`/`.parquet`, 14,179 rows, 1970-01-02 → 2026-06-19. |
| Add update script | Complete | `src/update_gold.py` delegates to `build_gold.main()` (full rebuild; the GLD splice can't be tail-stitched). |
| Add validation fixtures and tests | Complete | Schema, coverage, Close-vs-raw-LBMA, fee-model segment, and exact-GLD-tracking observed segment all tested. |
| Document methodology and caveats | Complete | Methodology, source registry, citations, manifest, validation, and log describe the GLD-tracking definition, the modeled fee drag, and the timing-basis caveat. |

### Short-Term U.S. Treasury / SHY-like 1-3 Year Government Bonds

Status: `complete_model_derived`

Target backtest alias: `STT`

Target definition: SHY-like exposure to short-duration nominal U.S. Treasury bonds, approximately 1-3 years remaining maturity, with coupon/distribution reinvestment reflected in `Adj Close` and `Total Return`.

Completion standard: the dataset must reach at least `1970-01-01` and include coupon-aware daily total returns. Public fund tickers cannot satisfy this by themselves because VFISX starts in 1991 and SHY starts in 2002. The implemented public-source method uses Federal Reserve nominal yield curve parameters to model a 2-year constant-maturity par Treasury total-return segment from 1970 until VFISX starts, then uses observed adjusted fund returns from VFISX and SHY. A constituent-level CRSP/WRDS build remains the preferred future upgrade.

| Milestone | Status | Notes |
| --- | --- | --- |
| Define SHY-like asset contract | Complete | The dataset should approximate SHY: short-duration nominal U.S. Treasuries, 1-3 year remaining maturity, total return with coupons/distributions reinvested. |
| Search and classify sources | Complete | SHY/iShares, Yahoo SHY, Yahoo VFISX, Federal Reserve nominal yield curve, and CRSP Treasury data have been classified. |
| Build provisional public fund-backed dataset | Complete | `data/processed/short_term_us_treasury.csv` uses VFISX adjusted returns from 1991-10-29 and SHY adjusted returns from 2002-07-31 onward. |
| Build 1970+ daily Treasury history | Complete | Uses Federal Reserve nominal yield curve parameters to model daily 2-year par Treasury price and coupon-carry total returns from 1970-01-02 until VFISX adjusted returns begin. |
| Add validation fixtures and tests | Complete | Added schema, coverage, arithmetic, Fed-model segment, and raw Yahoo segment-return tests. |
| Document methodology and caveats | Complete | Per-dataset methodology documents the Fed model-derived segment, VFISX/SHY source chain, and CRSP as a future constituent-level upgrade. |
| Add incremental update/stitching script | Complete | `src/update_short_term_us_treasury.py` rebuilds from current Yahoo chart data for the provisional public-source chain. |

### Intermediate-Term U.S. Treasury / IEF-like 7-10 Year Government Bonds

Status: `complete_model_derived`

Target backtest alias: `ITT`

Target definition: IEF-like exposure to intermediate-duration nominal U.S. Treasury bonds, approximately 7-10 years remaining maturity, with coupon/distribution reinvestment reflected in `Adj Close` and `Total Return`.

Completion standard: the dataset must reach at least `1970-01-01` and include coupon-aware daily total returns. Public fund tickers cannot satisfy this by themselves because VFITX starts in 1991 and IEF starts in 2002. The implemented public-source method uses Federal Reserve nominal yield curve parameters to model an 8.5-year constant-maturity par Treasury total-return segment from 1970 until VFITX starts, then uses observed adjusted fund returns from VFITX and IEF. A constituent-level CRSP/WRDS build remains the preferred future upgrade.

| Milestone | Status | Notes |
| --- | --- | --- |
| Define IEF-like asset contract | Complete | The dataset should approximate IEF: intermediate-duration nominal U.S. Treasuries, 7-10 year remaining maturity, total return with coupons/distributions reinvested. |
| Search and classify sources | Complete | IEF/iShares, Yahoo IEF, Yahoo VFITX, Federal Reserve nominal yield curve, and CRSP Treasury data have been classified. |
| Build provisional public fund-backed dataset | Complete | `data/processed/intermediate_term_us_treasury.csv` uses VFITX adjusted returns from 1991-10-29 and IEF adjusted returns from 2002-07-31 onward. |
| Build 1970+ daily Treasury history | Complete | Uses Federal Reserve nominal yield curve parameters to model daily 8.5-year par Treasury price and coupon-carry total returns from 1970-01-02 until VFITX adjusted returns begin. |
| Add validation fixtures and tests | Complete | Added schema, coverage, arithmetic, Fed-model segment, and raw Yahoo segment-return tests. |
| Document methodology and caveats | Complete | Per-dataset methodology documents the Fed model-derived segment, VFITX/IEF source chain, and CRSP as a future constituent-level upgrade. |
| Add incremental update/stitching script | Complete | `src/update_intermediate_term_us_treasury.py` rebuilds from current Yahoo chart data for the provisional public-source chain. |

### Long-Term U.S. Treasury / TLT-like 20+ Year Government Bonds

Status: `in_progress`

Target backtest alias: `LTT`

Target definition: TLT-like exposure to long-duration nominal U.S. Treasury bonds, approximately 20+ years remaining maturity, with coupon/distribution reinvestment reflected in `Adj Close` and `Total Return`.

Completion standard: the dataset must reach at least `1970-01-01` and include coupon-aware daily total returns. Public fund tickers cannot satisfy this by themselves because VUSTX starts in 1986 and TLT starts in 2002. The implemented public-source method uses Federal Reserve nominal yield curve parameters to model a 25-year constant-maturity par Treasury total-return segment from 1970 until VUSTX starts, then uses observed adjusted fund returns from VUSTX and TLT. A constituent-level CRSP/WRDS build remains the preferred future upgrade, but is not required for the current public-source model-derived dataset.

| Milestone | Status | Notes |
| --- | --- | --- |
| Define TLT-like asset contract | Complete | The dataset should approximate TLT: long-duration nominal U.S. Treasuries, primarily 20+ year remaining maturity, total return with coupons/distributions reinvested. |
| Search and classify sources | In progress | TLT/iShares, Yahoo TLT, Yahoo VUSTX, FRED DGS30, and CRSP Treasury data have been classified. More work is needed on licensed CRSP access. |
| Build provisional public fund-backed dataset | Complete | `data/processed/long_term_us_treasury.csv` uses VUSTX adjusted returns from 1986-05-19 and TLT adjusted returns from 2002-07-31 onward. |
| Build 1970+ daily Treasury history | Complete | Uses Federal Reserve nominal yield curve parameters to model daily 25-year par Treasury price and coupon-carry total returns from 1970-01-02 until VUSTX adjusted returns begin. |
| Add FRED model fallback for 1977-1986 if CRSP is unavailable | Not completed | FRED DGS30 can support a documented par-bond approximation, but this is not a substitute for constituent-level observed coupon-aware returns. FRED CSV retrieval timed out in this environment. |
| Add validation fixtures and tests | Complete | Added schema, coverage, arithmetic, Fed-model segment, and raw Yahoo segment-return tests. |
| Document methodology and caveats | Complete | Per-dataset methodology documents the Fed model-derived segment, VUSTX/TLT source chain, and CRSP as a future constituent-level upgrade. |
| Add incremental update/stitching script | Complete | `src/update_long_term_us_treasury.py` rebuilds from current Yahoo chart data for the provisional public-source chain. |

### Broad Commodities / DBC-like Diversified Futures Total Return

Status: `complete_model_derived_with_gsci_total_return_anchor_1970_1991`

Target backtest alias: `CMDTY`

Target definition: DBC-like broad diversified commodity futures total return. `Close`/`Price Return` = excess-return (spot+roll) level; `Adj Close`/`Total Return` = total-return level (excess + T-bill collateral). Coverage starts 1970-01-02 via the S&P GSCI **Total Return** anchor (roll yield + collateral + GSCI production weights). Segment 0 (1970-1983) log-linearly smooths the anchor to daily `^IRX` dates; Segment 1 (1984-1991) overlays the genuine daily `^SPGSCI` spot shape onto the anchor.

| Milestone | Status | Notes |
| --- | --- | --- |
| Define commodity asset contract | Complete | `Close` = excess return level (no collateral); `Adj Close` = total return level (excess + T-bill collateral). |
| Search and classify sources | Complete | S&P GSCI Total Return anchor (MacroMicro static file), `^SPGSCI` (daily shape), `^BCOM`, DBC, `^IRX` active; World Bank model superseded; AQR equal-weight rejected; licensed daily GSCI/BCOM TR are upgrade candidates. |
| Verify `^BCOM` index type (Spot vs Excess Return) | Complete | 2021 annual return of 27.06% matches BCOM Excess Return (~27.1%); confirmed `^BCOM` includes spot + roll yield. |
| Design source chain | Complete | GSCI TR anchor smoothed (1970-1984) -> GSCI TR anchor + ^SPGSCI spot shape (1984-1991) -> BCOM ER + IRX (1991-2006) -> DBC observed (2006-present). |
| Implement `src/build_broad_commodities.py` | Complete | Fetches four Yahoo tickers, loads the static GSCI TR anchor, builds anchor-smoothed / overlay segments, writes CSV/Parquet/metadata. |
| Implement `src/update_broad_commodities.py` | Complete | Calls `main()` from build script; rebuilds full chain (GSCI anchor static, DBC tail live). |
| Run build and inspect outputs | Complete | 14,163 rows 1970-01-02 to 2026-06-25; GSCI_SMOOTH=3487, GSCI_SHAPE=1768, BCOM=3781, DBC=5127. Adj Close tracks the anchor within ~2%; Segment 1 vol ~16%/yr. |
| Add validation tests | Complete | 12 tests covering schema, coverage, arithmetic, Adj>=Close, GSCI anchor growth + tracking, Segment 1 de-smoothing, DBC/BCOM raw-source match, and flag counts. |
| Write documentation | Complete | `docs/methodology_cmdty.md`, updated index, source registry, validation, PLAN, LOG, HANDOVER, manifest, citations. |
| Replace World Bank monthly spot model + spot-only GSCI segment with S&P GSCI Total Return anchor | Complete (2026-06-26) | Adds roll yield (~9%/yr 1984-91) + collateral + GSCI weights to 1970-1991; Segment 1 de-smoothed onto ^SPGSCI spot shape. Previous spot-only segment understated the era ~3x. |
| Upgrade anchor with licensed daily GSCI Total Return | Candidate upgrade | A licensed daily S&P GSCI TR feed would remove the downsampling/smoothing; a constituent-level futures reconstruction is the deeper upgrade. |

### U.S. CPI-U Inflation Index / CPI

Status: `complete_model_derived_from_monthly_cpi`

Target backtest/utility alias: `CPI`

Target definition: U.S. CPI-U, all urban consumers, U.S. city average, all items, seasonally adjusted. This is a daily portfolio deflator, not an investable asset.

| Milestone | Status | Notes |
| --- | --- | --- |
| Define CPI contract | Complete | `Close` and `Adj Close` are CPI-U index levels; returns are daily inflation rates implied by the level. |
| Search and classify sources | Complete | BLS `CUSR0000SA0` active; FRED `CPIAUCSL` validation/reference. |
| Build daily deflator | Complete | Monthly CPI is expanded to calendar days by constant log interpolation and flagged as model-derived. Latest monthly observation is carried forward until the next release. |
| Add validation tests | Complete | Tests cover schema, calendar coverage, return arithmetic, exact BLS month-start matches, and interpolation/carry flags. |
| Wire portfolio script | Complete | `external backtesting application` can load the local CPI dataset for real backtesting analysis. |

### Global All-World Stocks / GLSTOCK

Status: `complete_model_derived_public_source_proxy`

Target backtest alias: `GLSTOCK`

Target definition: broad global all-world equity total return in USD, akin to VT, MSCI ACWI, or FTSE All-World.

| Milestone | Status | Notes |
| --- | --- | --- |
| Define global stock contract | Complete | `Close == Adj Close`; single normalized total-return proxy level. |
| Search and classify sources | Complete | Licensed ACWI/FTSE daily history is candidate upgrade; public chain uses MSCI annual returns, USLCAP, French developed daily factors, and VT. |
| Build 1970+ dataset | Complete | 14,396 rows from 1970-01-02 to 2026-06-18. |
| Add validation tests | Complete | Tests cover schema, coverage, arithmetic, MSCI annual target matching, raw French daily matching, and raw VT matching. |
| Wire portfolio script | Complete | `external backtesting application` includes `GLSTOCK` as a local custom dataset. |

### Unhedged Global Bonds / GLBOND

Status: `complete_model_derived_public_source_proxy`

Target backtest alias: `GLBOND`

Target definition: unhedged global bond total-return proxy in USD. Early history is a GDP-weighted developed-market government-bond basket whose daily path comes from observed daily FX (BIS) and observed monthly yields (OECD MEI), anchored each year to the JST annual basket; observed history blends U.S. aggregate bonds and unhedged international sovereign bonds.

| Milestone | Status | Notes |
| --- | --- | --- |
| Define global bond contract | Complete | `Close == Adj Close`; single normalized total-return proxy level. |
| Search and classify sources | Complete | JST annual government-bond returns active (annual anchor + GDP weights); BIS daily FX and OECD MEI monthly yields active (early-segment path, via DBnomics); BND/BWX active observed blend; licensed global index history is candidate upgrade. |
| Build 1970+ dataset | Complete | 14,236 rows from 1970-01-02 to 2026-06-18. |
| De-smooth 1970-2007 segment | Complete | Replaced the flat annual ramp with a JST-anchored daily-FX + monthly-yield reconstruction. Genuine daily variation; correctly-timed FX events (Plaza 1985, 1978 dollar rescue). |
| Fix GDP weighting | Complete | Switched basket weights from JST nominal `gdp`/`xrusd` (inconsistent units -> small economies dominated, US ~0.3%) to comparable real GDP `rgdpmad`x`pop` (US ~42%, JP ~16%). Moved the annual anchor 6-10pp/year. Early-segment vol now ~5% (US-heavy, no FX on the US leg). |
| Daily rate leg (US/JP/UK) | Complete | Replaced the monthly within-month rate distribution with genuine daily bond TR for the three largest weights: in-repo US Treasury (1970+), MoF Japan 10y (1986-07+), BoE UK 10y spot (1979+); ≈62% of the basket daily from 1979. Others stay monthly (OECD). Germany probed: free daily only from 1997, so left monthly. Early-segment vol ~5.9%. |
| Add validation tests | Complete | Tests cover schema, coverage, arithmetic, the JST per-year anchor invariant, raw BND/BWX blend matching, and de-smoothing regressions (distinct daily returns, realistic vol band, FX-event directions). |
| Wire portfolio script | Complete | `external backtesting application` includes `GLBOND` as a local custom dataset. |

### Unhedged Global Short-Term (1-3yr) Government Bonds / GLSTBOND

Status: `complete_model_derived_public_source_proxy`

Target backtest alias: `GLSTBOND`

Target definition: unhedged global short-term (1-3yr) government-bond total-return proxy in USD - ISHG-like in maturity but global in scope (includes the US); the short-duration sibling of `GLBOND`. `Close`/`Price Return` are gross of fees; `Adj Close`/`Total Return` are net of a representative ~0.26%/yr fund expense drag (the investable series).

| Milestone | Status | Notes |
| --- | --- | --- |
| Define short-bond contract | Complete | Constant-maturity 2yr (mid 1-3yr); global incl. US; unhedged; modeled fees (Close gross, Adj Close net). |
| Search and classify sources | Complete | Verified short-end coverage: MoF 2yr JGB from 1974-09, OECD `IR3TIB01`/`IRLTLT01` for 2yr interpolation, JST `stir`/`ltrate` early fallback, BoE 2yr, in-repo STT (US). Observed: SHY + ISHG/BWZ from 2009. |
| Build 1970+ dataset | Complete | 14,233 rows 1970-01-02 to 2026-06-15; direct construction (no JST overlay). Model 9,864 / observed 4,369. |
| Modeled fees | Complete | Adj Close net of ~0.26%/yr; implied drag measured at 0.2605%/yr. Observed era adds the fee back to keep Close gross. |
| GDP-weighted observed blend | Complete | `w_us`*SHY + `(1-w_us)`*mean(ISHG,BWZ), `w_us` = US share of developed real GDP (0.20→0.46), annually rebalanced, carried forward past JST. |
| Add validation tests | Complete | 13 tests: schema, coverage, dual-column arithmetic, fee drag, observed blend exact match, genuinely-daily path, vol band 3-12%, FX-event directions, sane weights, daily 2yr coverage (US 1970/JP 1974/UK 1979). |
| Wire portfolio script | To do | Register `GLSTBOND` alias in the portfolio script (user step). |

## Derived Leveraged Datasets

Status: in progress. `USLCAP3X` (UPRO-like 3x large cap), `LTT3X` (TMF-like 3x long Treasury), `ITT3X` (TYD-like 3x intermediate Treasury), and `GOLD2X` (UGL-like 2x gold) are complete and model-derived; remaining tiers are planned.

Purpose: create long-horizon daily datasets that mimic common daily-reset leveraged ETFs using the project's existing 1970+ base asset-class datasets. These must be treated as derived model datasets before live ETF inception, not as observed fund history.

### 3x U.S. Large Cap / UPRO-like

Status: `complete_model_derived`

Target backtest alias: `USLCAP3X`

Target definition: 3x the daily total return of the S&P 500, reset daily, net of financing on the borrowed (2x) exposure and a ProShares-style expense ratio (UPRO). Synthetic model from 1970-01-02 to UPRO inception (2009-06-25), observed UPRO adjusted-close returns thereafter. `Close == Adj Close` (single 3x total-return NAV normalized to 100).

| Milestone | Status | Notes |
| --- | --- | --- |
| Define UPRO-like 3x daily-reset asset contract | Complete | Underlying = USLCAP total return; daily reset; financing on 2x borrowed exposure; 0.91% ER. |
| Search and classify sources | Complete | USLCAP base (underlying), Yahoo `^IRX` (financing benchmark), Yahoo `UPRO` (validation + observed). |
| Implement `src/build_us_large_cap_3x_sp500.py` | Complete | Daily-reset compounding with `^IRX`+spread financing (actual/360) and expense (actual/365), spliced to observed UPRO returns. |
| Calibrate financing spread vs UPRO overlap | Complete | Spread 0.65% over `^IRX`; daily corr 0.998, ann. TE ~3.2%, cumulative ratio model/UPRO ~1.0000. |
| Implement `src/update_us_large_cap_3x_sp500.py` | Complete | Rebuilds full chain from current USLCAP CSV + fresh `^IRX`/`UPRO`. |
| Run build and inspect outputs | Complete | 14,234 rows 1970-01-02 to 2026-06-15; synthetic 9,966, observed UPRO 4,268. 1987-10-19 ≈ -57% leveraged day survives positive. |
| Add validation tests | Complete | Schema, coverage, arithmetic, segment flags, raw UPRO segment match, independent synthetic-model recompute, live-overlap tracking. |
| Write documentation | Complete | `docs/methodology_uslcap3x.md`, index, source registry, validation, manifest, citations, PLAN, LOG, HANDOVER. |
| Register `USLCAP3X` alias in `external backtesting application` | Pending | External backtesting script; add alias pointing to `us_large_cap_3x_sp500.csv`. |

### 3x Long-Term Treasury / TMF-like

Status: `complete_model_derived`

Target backtest alias: `LTT3X`

Target definition: 3x the daily total return of a TLT-like long-term (20+ year) U.S. Treasury series, reset daily, net of financing on the borrowed (2x) exposure and a Direxion-style expense ratio (TMF). Synthetic model from 1970-01-02 to TMF inception (2009-04-16), observed TMF adjusted-close returns thereafter. `Close == Adj Close` (single 3x total-return NAV normalized to 100).

| Milestone | Status | Notes |
| --- | --- | --- |
| Define TMF-like 3x daily-reset asset contract | Complete | Underlying = LTT total return; daily reset; financing on 2x borrowed exposure; ~1.06% ER. |
| Search and classify sources | Complete | LTT base (underlying), Yahoo `^IRX` (financing benchmark), Yahoo `TMF` (validation + observed). |
| Implement `src/build_long_term_treasury_3x.py` | Complete | Daily-reset compounding with `^IRX`+spread financing (actual/360) and expense (actual/365), spliced to observed TMF returns. |
| Calibrate financing spread vs TMF overlap | Complete | Spread 0.53% over `^IRX`; daily corr 0.997, ann. TE ~3.7%, cumulative ratio model/TMF ~1.0004. |
| Implement `src/update_long_term_treasury_3x.py` | Complete | Rebuilds full chain from current LTT CSV + fresh `^IRX`/`TMF`. |
| Run build and inspect outputs | Complete | 14,174 rows 1970-01-02 to 2026-06-15; synthetic 9,857, observed TMF 4,317. Documented pre-2002 duration mismatch and leverage decay. |
| Add validation tests | Complete | Schema, coverage, arithmetic, segment flags, raw TMF segment match, independent synthetic-model recompute, live-overlap tracking. |
| Write documentation | Complete | `docs/methodology_ltt3x.md`, index, source registry, validation, manifest, citations, PLAN, LOG, HANDOVER. |
| Register `LTT3X` alias in `external backtesting application` | Done | Registered by user in the external backtesting script. |

### 3x Intermediate-Term Treasury / TYD-like

Status: `complete_model_derived`

Target backtest alias: `ITT3X`

Target definition: 3x the daily total return of an IEF-like intermediate-term (7-10 year) U.S. Treasury series, reset daily, net of financing on the borrowed (2x) exposure and a Direxion-style expense ratio. Synthetic model from 1970-01-02 to TYD inception (2009-04-16), observed TYD adjusted-close returns thereafter. `Close == Adj Close` (single 3x total-return NAV normalized to 100).

Naming note: the genuine 3x 7-10yr ETF is Direxion **TYD**. ProShares **UST** is a **2x** fund (the backlog's "3x UST" label was wrong); UST is the future target for a separate `ITT2X`.

| Milestone | Status | Notes |
| --- | --- | --- |
| Define TYD-like 3x daily-reset asset contract | Complete | Underlying = ITT total return; daily reset; financing on 2x borrowed exposure; ~1.09% ER. |
| Search and classify sources | Complete | ITT base (underlying), Yahoo `^IRX` (financing benchmark), Yahoo `TYD` (validation + observed); UST rejected as 2x. |
| Implement `src/build_intermediate_treasury_3x.py` | Complete | Daily-reset compounding with `^IRX`+spread financing (actual/360) and expense (actual/365), spliced to observed TYD returns. |
| Calibrate financing spread vs TYD overlap | Complete | Spread 0.19% over `^IRX`; cumulative ratio model/TYD ~0.9998. Daily corr only ~0.88 full-overlap (TYD stale-price noise 2014-2018); clean-era (2019+) corr > 0.95. |
| Implement `src/update_intermediate_treasury_3x.py` | Complete | Rebuilds full chain from current ITT CSV + fresh `^IRX`/`TYD`. |
| Run build and inspect outputs | Complete | 14,158 rows 1970-01-02 to 2026-06-15; synthetic 9,841, observed TYD 4,317. Synthetic 2009 level ~5,000 (vs LTT3X ~650) illustrates lower leverage decay for lower-vol intermediate Treasuries. |
| Add validation tests | Complete | Schema, coverage, arithmetic, segment flags, raw TYD segment match, independent synthetic-model recompute, cumulative + clean-era-correlation overlap checks. |
| Write documentation | Complete | `docs/methodology_itt3x.md`, index, source registry, validation, manifest, citations, PLAN, LOG, HANDOVER. |
| Register `ITT3X` alias in `external backtesting application` | Done | Registered by user in the external backtesting script. |

### 2x Gold / UGL-like

Status: `complete_model_derived`

Target backtest alias: `GOLD2X`

Target definition: 2x the daily performance of gold, reset daily, net of financing on the borrowed (1x) exposure and a ProShares-style expense ratio (UGL). Synthetic model from 1970-01-02 to UGL inception (2008-12-03), observed UGL adjusted-close returns thereafter. `Close == Adj Close` (single 2x total-return NAV normalized to 100). Underlying is `GOLDPM`'s pure-spot **`Price Return`** (not its now-fee-dragged Total Return); the series follows the gold (LBMA) trading calendar. After inception, US-market holidays where UGL did not trade are held flat (not synthetic-filled) — a holiday double-count that inflated GOLD2X +33.8% vs UGL was fixed 2026-06-20, and the observed era now tracks UGL exactly.

| Milestone | Status | Notes |
| --- | --- | --- |
| Define UGL-like 2x daily-reset asset contract | Complete | Underlying = GOLDPM spot total return; daily reset; financing on 1x borrowed exposure; 0.95% ER. |
| Search and classify sources | Complete | GOLDPM base, Yahoo `^IRX` (financing), Yahoo `UGL` (validation + observed), Yahoo `GLD` (timing cross-check). |
| Implement `src/build_gold_2x.py` | Complete | Daily-reset compounding with `^IRX`+spread financing (actual/360) and expense (actual/365), spliced to observed UGL returns; gold-calendar with US-holiday model fills. |
| Calibrate financing spread vs UGL overlap | Complete | Spread 0.93% over `^IRX` (absorbs gold futures roll/storage); cumulative ratio model/UGL ~1.0007; daily corr ~0.67 (LBMA-fix vs US-close timing), vol match ~1.0. |
| Implement `src/update_gold_2x.py` | Complete | Rebuilds full chain from current GOLDPM CSV + fresh `^IRX`/`UGL`. |
| Run build and inspect outputs | Complete | 14,175 rows 1970-01-02 to 2026-06-15; synthetic 9,883 (incl. ~97 US-holiday fills), observed UGL 4,292. Confirmed timing basis via GLD (UGL vs 2x-GLD corr 0.997). |
| Add validation tests | Complete | Schema, coverage, arithmetic, segment flags, raw UGL segment match, independent synthetic-model recompute, cumulative + volatility-ratio overlap checks. |
| Write documentation | Complete | `docs/methodology_gold2x.md`, index, source registry, validation, manifest, citations, PLAN, LOG, HANDOVER. |
| Register `GOLD2X` alias in `external backtesting application` | Pending | External backtesting script; add alias pointing to `gold_2x.csv`. |

| Target | Leverage | Base Dataset | Live ETF Validation | Notes |
| --- | ---: | --- | --- | --- |
| UPRO-like U.S. large cap | 3x | `USLCAP` | UPRO adjusted close | Daily reset large-cap equity model; include financing, fee, and tracking-drag assumptions. |
| SSO-like U.S. large cap | 2x | `USLCAP` | SSO adjusted close | Useful lower-leverage companion to the UPRO-like dataset. |
| TMF-like long Treasury | 3x | `LTT` | TMF adjusted close | Validate overlap carefully; document duration and derivatives-exposure mismatch against the constant-maturity LTT base. |
| UBT-like long Treasury | 2x | `LTT` | UBT adjusted close | Same LTT base, lower leverage. |
| TYD-like intermediate Treasury | 3x | `ITT` | TYD adjusted close | Daily reset intermediate Treasury model. Direxion TYD is the genuine 3x 7-10yr ETF. Built as `ITT3X`. |
| UST-like intermediate Treasury | 2x | `ITT` | UST adjusted close | Same ITT base, lower leverage. ProShares UST is a 2x fund (earlier "3x UST" label was incorrect). |
| UGL-like gold | 2x | `GOLDPM` (LBMA PM spot) | UGL adjusted close | Built as `GOLD2X`. Base is LBMA PM spot; daily UGL correlation limited (~0.67) by LBMA-fix vs US-close timing — calibrated on cumulative growth + volatility. |
| Leveraged broad commodities | 2x/3x | `CMDTY` | candidate ETF/ETN overlap if available | Only after `CMDTY` alias registration and explicit acceptance of CMDTY's source-chain caveats. |

Minimum methodology requirements:

- Use daily-reset arithmetic: `leveraged_return = leverage * underlying_total_return - daily_financing_drag - daily_fee_drag - optional_tracking_drag`.
- Define financing-rate source, borrowing spread, fund expense ratio, and any extra tracking-drag calibration before building.
- Keep derived leveraged outputs separate from base asset-class datasets.
- Use clear aliases and dataset identifiers, for example `USLCAP3X`, `LTT3X`, `ITT3X`, `GOLD2X`.
- Add `Quality Flag` values that distinguish synthetic pre-inception model periods from observed ETF-validation periods.
- Validate each live overlap against the corresponding ETF adjusted-close returns, including daily-return agreement, cumulative-return error, CAGR, volatility, max drawdown, and tracking error.
- Document path-dependence and volatility decay; leveraged datasets must not be described as simple multiples of long-horizon base returns.
- Add build/update scripts, manifests, citations, methodology pages, validation tests, and backtesting aliases for each derived dataset.

## Dataset Update Method

Each dataset should have an update script that can append current observations without rebuilding the full history every time.

For U.S. large-cap equities:

- Use `src/update_us_large_cap_sp500.py`.
- Read the existing processed CSV.
- Refetch a configurable overlap window ending on the requested end date from a Yahoo-compatible API source.
- Prefer yfinance-compatible/Yahoo chart data for current observations because it matches the output contract.
- Merge by `Date`, keeping the newly fetched row when dates overlap.
- Recompute return columns after stitching rather than trusting partial-window returns.
- Rewrite CSV and Parquet outputs together so they remain synchronized.
- Update build metadata with row count, date range, checksum, and whether Parquet was written.
- For adjusted/total-return data, preserve full daily coverage from the first trading observation after `1970-01-01`; do not use monthly interpolation or dividend estimates.

For short-term U.S. Treasuries:

- The current public-source 1970+ dataset uses Federal Reserve nominal yield curve parameters to model a 2-year constant-maturity par Treasury total-return segment before public fund data exists.
- A future constituent-level upgrade should be built from daily Treasury issue-level data, preferably CRSP/WRDS, selecting bonds with 1-3 years remaining maturity.
- Use SHY adjusted returns for post-2002 public validation and VFISX adjusted returns as a pre-SHY public proxy check.

For intermediate-term U.S. Treasuries:

- The current public-source 1970+ dataset uses Federal Reserve nominal yield curve parameters to model an 8.5-year constant-maturity par Treasury total-return segment before public fund data exists.
- A future constituent-level upgrade should be built from daily Treasury issue-level data, preferably CRSP/WRDS, selecting bonds with 7-10 years remaining maturity.
- Use IEF adjusted returns for post-2002 public validation and VFITX adjusted returns as a pre-IEF public proxy check.

For long-term U.S. Treasuries:

- The current public-source 1970+ dataset uses Federal Reserve nominal yield curve parameters to model a 25-year constant-maturity par Treasury total-return segment before public fund data exists.
- A future constituent-level upgrade should be built from daily Treasury issue-level data, preferably CRSP/WRDS.
- Select nominal U.S. Treasury bonds with remaining maturity of at least 20 years, excluding TIPS, bills, strips, and non-standard issues unless a benchmark methodology requires them.
- Compute daily holding-period returns from clean/dirty prices and coupon cash flows, then market-value weight eligible bonds to form a TLT-like total-return index.
- Use TLT adjusted returns for post-2002 public validation and VUSTX adjusted returns as a pre-TLT public proxy check, not as the final 1970 source.
- If CRSP is unavailable, a FRED DGS30 par-bond model may be added as a clearly labelled approximation, but it must not be marked complete as an observed 1970+ TLT-like dataset.
