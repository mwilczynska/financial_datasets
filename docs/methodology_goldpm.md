# GOLDPM — Gold (GLD-tracking, LBMA PM spot extended to 1970)

Dataset identifier: `gold`

Backtest alias: `GOLDPM`

Status: production dataset built; tracks SPDR Gold Shares (`GLD`) including fees

## Asset Definition

`GOLDPM` is designed to behave like an investment in the SPDR Gold Shares ETF (`GLD`) —
**including GLD's fee/expense drag** — extended back to 1970, long before GLD's 2004 inception.
This lets long-horizon backtests be consistent with actually holding `GLD`.

- `Close`: LBMA Gold Price PM in USD per troy ounce — the recognizable **pure spot price** of
  gold, kept fee-free across the whole 1970→now history. `Price Return` is its daily return and
  is therefore the pure spot return.
- `Adj Close`: a **GLD-tracking total-return index**:
  - 1970-01-02 → GLD inception (2004-11-18): pure spot return **minus GLD's expense drag**
    (0.40%/yr, accrued actual/365). Models what GLD would have returned had it existed.
  - From GLD inception onward: **observed GLD adjusted-close daily returns**. `Adj Close` is
    exactly proportional to GLD's adjusted close in this segment — the modern era *is* GLD.
  - `Total Return` is the daily return of `Adj Close`.

Because `Adj Close` carries the fee drag, it diverges below `Close` over time; the two are **no
longer equal** (this is the deliberate change from the earlier pure-spot definition).

### Why two return columns

The pure-spot `Price Return` is retained because the derived 2x dataset (`gold_2x` / `GOLD2X`)
builds on it: a leveraged gold fund tracks the gold *price*, then applies its own financing and
fee. Using `Price Return` as the 2x base ensures fund fees are counted exactly once (the GLD
expense drag in GOLDPM's `Total Return` is not propagated into the 2x model).

## Output Files

| File | Path |
|---|---|
| CSV | `data/processed/gold.csv` |
| Parquet | `data/processed/gold.parquet` |
| Manifest | `sources/manifests/gold.yml` |
| Citation notes | `sources/citations/gold.md` |
| Build script | `src/build_gold.py` |
| Update script | `src/update_gold.py` |
| Test file | `tests/validation/test_gold_contract.py` |

Coverage starts on `1970-01-02`, the first available LBMA PM observation after the `1970-01-01`
anchor.

## Source Chain

| Segment | Dates | Calendar | Source | `Adj Close` construction |
|---|---|---|---|---|
| Model (GLD-tracking) | 1970-01-02 → before GLD inception | LBMA (London) | LBMA Gold Price PM (spot) | spot return × (1 − 0.40%·days/365) |
| Observed GLD | GLD inception → present | **NYSE (GLD days)** | Yahoo `GLD` adjusted close | GLD daily total return; `Adj Close` ∝ GLD |

### Calendar handling (why the observed era is on the NYSE calendar)

GLD trades on the US/NYSE calendar; the LBMA fix is on the London calendar. The two differ — UK
bank holidays (Easter Monday, early May, August bank holiday, Boxing Day, …) and US market
holidays don't line up. A backtester that compares two series by **intersecting their daily-return
dates and compounding** (which is exactly how the external backtesting scripts compare them) will, on
every calendar-mismatch day, drop one series' return while the other folds the move into a spanning
return. With GOLDPM on the London calendar this produced a spurious **+1.96%/yr (+47% cumulative)**
GOLDPM-vs-GLD gap over 2004-2026, even though the *levels* were perfectly proportional.

So the **observed era runs on GLD's (NYSE) trading calendar**: one row per GLD trading day, `Adj
Close = scale · GLD_adj`. This makes the dataset align with GLD day-for-day, so a return-based
backtest reproduces GLD with no calendar drift.

- `Close` is the LBMA PM fix on days London fixed (the vast majority).
- On NYSE-open / LBMA-closed days (UK bank holidays, ~6/yr, flag
  `observed_gld_us_open_lbma_holiday_close_gld_step`) there is no LBMA fix, so `Close` is **stepped
  by GLD's move** from the prior row (gold traded globally even though London didn't fix). Across
  the gap this telescopes back to the next LBMA fix, keeping `Close` anchored to the LBMA series
  while leaving `Price Return` realistic.

The pre-2004 **model era stays on the LBMA calendar** (there is no US ETF to align with then; it is
a fee-dragged model). Putting the model era on the NYSE calendar too is a possible future tidy-up.

## Production Sources

- **LBMA Gold Price PM JSON** (`https://prices.lbma.org.uk/json/gold_pm.json`): daily PM gold
  prices back before 1970; first value in each row's `v` array is USD per troy ounce. Drives
  `Close`/`Price Return` throughout and the modeled `Adj Close` pre-2004.
- **Yahoo `GLD` chart API**: SPDR Gold Shares adjusted close, drives `Adj Close` from 2004-11-19.

## Validation / Reference Sources

- **GLD expense ratio (0.40%)**: the modeled fee drag. Corroborated by the observed GLD-vs-spot
  underperformance over the live overlap (~0.42%/yr mean daily difference, full-window gap
  ~0.49%/yr).
- **LBMA Gold Price AM JSON**: same-administrator sanity reference; not independent.
- **FRED `GOLDPMGBD228NLBM`**: candidate validation; likely mirrors the same London PM benchmark.

## Rejected or Limited Sources

- **Stooq / COMEX continuous futures (US-close base)**: a US-close gold base (e.g. `GC=F`, ~1:30pm
  ET settle) would raise *daily* correlation with GLD from ~0.65 (PM fix) to ~0.89, but Stooq is
  blocked in this environment and Yahoo `GC=F` only reaches 2000. The timing basis is zero-mean
  for cumulative return, so this is a daily-fidelity upgrade only, deferred until a futures source
  is available. See caveats.

## Build Method

1. Fetch the LBMA Gold Price PM JSON (`sources/raw/gold_lbma_gold_pm.json`) and the Yahoo `GLD`
   chart (`sources/raw/gold_yahoo_gld_chart.json`).
2. For each LBMA observation ≥ 1970-01-01: set `Close` = USD PM fixing; `Price Return` = daily
   return of `Close`.
3. Build `Adj Close` as a running index anchored at the first `Close`:
   - Pre-GLD: multiply by spot gross return × `(1 − 0.0040·days/365)`.
   - Splice at GLD inception (continuous level): fix `scale = level / GLD_adj`, then
     `Adj Close = scale · GLD_adj`. Hold flat on US-holiday rows where GLD did not trade.
4. `Total Return` = daily return of `Adj Close`.
5. Set per-segment `Source` / `Quality Flag` / `Source Notes`.
6. Write CSV (interim + processed), Parquet, and build metadata.

## Update Method

`src/update_gold.py` delegates to `build_gold.main()` and rebuilds the full chain from scratch
(refetching the LBMA PM JSON and the GLD chart). The GLD splice cannot be incrementally
re-stitched by a simple tail replacement, so a full rebuild keeps the continuous-level splice and
the holiday handling correct.

## Tests

`tests/validation/test_gold_contract.py` covers:

- Yahoo-compatible schema and required columns.
- Coverage from the first observation after 1970-01-01; unique, sorted dates.
- Positive `Close` and `Adj Close`; `Adj Close == Close` on row 1 and `Adj Close < Close` at the
  end (fee drag present).
- `Price Return` recomputes from `Close`; `Total Return` recomputes from `Adj Close`.
- `Close` exactly matches the raw LBMA PM source (> 10,000 rows).
- Model segment: `Total Return == spot price return − GLD expense accrual` (actual/365).
- Observed segment: `Adj Close` is exactly proportional to raw `GLD` adjusted close (tracking is
  perfect to within 1e-9), and the observed-era dates are **exactly GLD's trading days** (so a
  backtester's date intersection keeps every GLD day — no calendar drift). UK-bank-holiday rows
  (`..._close_gld_step`) carry a GLD-stepped `Close`, not an LBMA fix.

## Independent Check Findings

Over the GLD overlap (2004-11-18 → 2026-06-19) the **redefined** `Adj Close` tracks `GLD` exactly
(CAGR gap 0.0000%, constant level ratio). For reference, the previous pure-spot definition
*outperformed* GLD by ~0.49%/yr over the same window — essentially all of which was GLD's 0.40%
expense ratio, the rest zero-mean timing noise. The redefinition folds that fee in so the series
matches GLD.

## Caveats

- **Includes GLD fees by design.** `Adj Close` is intentionally *not* pure spot; it carries
  GLD's expense drag so it matches a real GLD holding. Use `Close` / `Price Return` for pure spot.
- **Timing basis (daily only).** Pre-2004 the model is struck at the LBMA PM fix (~10am ET), not
  the US 4pm close. This degrades day-to-day alignment with US-close gold instruments but does not
  bias cumulative return. A US-close base (COMEX futures) is a future daily-fidelity upgrade.
- **Calendars switch at 2004.** The model era is on the London calendar, the observed era on the
  NYSE calendar. For GLD/UGL comparisons (entirely in the observed era) this is exact; a pre-2004
  multi-asset backtest still mixes London-calendar gold with NYSE-calendar US assets (a small,
  pre-existing approximation that moving the model era to the NYSE calendar would remove).
- **Pre-2004 is a model**, not observed GLD history; flagged `model_gld_tracking_...`.
