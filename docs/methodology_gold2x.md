# Methodology — GOLD2X (2x Daily-Reset Gold, UGL-like)

## Identifier and alias

- Dataset identifier: `gold_2x`
- Backtest alias: `GOLD2X`
- Type: **derived leveraged dataset** (model-derived before UGL inception; observed UGL returns after).

## Asset definition

`GOLD2X` models a 2x daily-reset leveraged gold fund — ProShares Ultra Gold (`UGL`) — extended
back to 1970, before UGL's 2008-12-03 inception.

- `Close` and `Adj Close` are **equal**: a synthetic daily-reset leveraged fund has no separate
  price index, so the single series is the (total-return) NAV level normalized to 100 on
  1970-01-02.
- `Price Return` equals `Total Return`.
- `Open`, `High`, `Low`, and `Volume` are blank.

This is a derived model, not observed UGL history before 2008, and must be flagged as such.

## Output files

| Artifact | Path |
|---|---|
| CSV | `data/processed/gold_2x.csv` |
| Parquet | `data/processed/gold_2x.parquet` |
| Manifest | `sources/manifests/gold_2x.yml` |
| Build metadata | `sources/manifests/gold_2x_build.json` |
| Citations | `sources/citations/gold_2x.md` |
| Build script | `src/build_gold_2x.py` |
| Update script | `src/update_gold_2x.py` |
| Tests | `tests/validation/test_gold_2x_contract.py` |

## Coverage

- First observation: `1970-01-02` (base level 100).
- Last observation: most recent UGL trading day from Yahoo.
- Current build: 14,200 rows, 1970-01-02 to 2026-06-18. Synthetic rows 9,789 (all pre-inception);
  observed UGL rows 4,411; US-holiday flat rows 0 (observed era on the NYSE calendar). UGL
  inception 2008-12-03.

## Sources

- **Underlying** (`active`): `GOLDPM` (`data/processed/gold.csv`) **`Price Return`** column — the
  pure LBMA Gold Price PM spot return, from 1970-01-02. (GOLDPM's `Total Return` now carries GLD's
  0.40% expense drag; the 2x fund builds on the pure-spot price return and applies its own
  financing/fee so costs are counted once.)
- **Financing benchmark** (`active`): Yahoo `^IRX` 13-week T-bill discount yield.
- **Observed ETF / calibration target** (`active_from_2008`): Yahoo `UGL` adjusted close.
- **Timing cross-check** (`validation`): Yahoo `GLD` (US-close gold ETF) — used only to diagnose
  the timing basis, not in the production build.
- **Parameter reference**: ProShares UGL prospectus (2x daily gold; 0.95% ER).

## Build method

Same daily-reset construction as the other leveraged datasets, with `L = 2` and the `GOLDPM`
pure-spot `Price Return` (`u`) base:

```
financing_daily = (IRX_t/100 + spread) * days_t / 360
expense_daily   = expense_ratio * days_t / 365
lev_ret_t       = 2 * u_t - 1 * financing_daily - expense_daily   # u = GOLDPM Price Return
level_t         = level_{t-1} * (1 + lev_ret_t)      # starts at 100
```

- `spread = 0.0093` (calibrated to the UGL overlap); `expense_ratio = 0.0095`.
- Synthetic segment runs 1970-01-02 through and including UGL's first trading day; from the next
  trading day the dataset uses observed UGL adjusted-close returns, computed against the most
  recent UGL close. Levels compound continuously.
- A `-0.9999` non-positivity floor exists but never triggers (worst day ≈ -27%, the Jan 1980 gold
  crash, well above -100%).

### Trading-calendar handling (inherits GOLDPM's NYSE observed calendar)

`GOLD2X` iterates the `GOLDPM` dates, so it inherits GOLDPM's calendar: the **model era is on the
LBMA calendar and the observed era on the NYSE (GLD/UGL) calendar**. Because the observed era is
already on the NYSE calendar, every observed `GOLD2X` row lands on a UGL trading day, so `Adj Close`
is an exact constant multiple of UGL (CAGR gap 0.0000%, guarded by
`test_observed_dataset_tracks_ugl_cumulatively`). The holiday-flat path
(`observed_ugl_us_holiday_flat`) is retained as a safety net but is effectively never needed now
(0 rows in the current build).

> **Two bugs fixed (2026-06-20).** (1) *Holiday double-count:* the earlier build filled LBMA-open /
> US-closed holidays with a synthetic 2x-gold day **and** let UGL's reopen return span the same
> holiday, inflating GOLD2X **+33.8% / +1.89%/yr above UGL** over 2008-2026. (2) *Calendar mismatch:*
> with GOLDPM on the London calendar, a return-intersection backtest drifted GOLD2X vs UGL by
> ~+2%/yr on UK-bank-holiday days. Both are resolved by GOLDPM's observed era moving to the NYSE
> calendar (GOLD2X inherits it): observed GOLD2X now reproduces UGL exactly in a return-based
> backtest.

### Quality flags

| Flag | Segment |
|---|---|
| `model_2x_daily_reset_synthetic_from_goldpm_spot_price_return_minus_financing_and_fee` | 1970-01-02 → UGL inception day |
| `observed_ugl_etf_adjusted_total_return` | UGL trading days after inception |
| `observed_ugl_us_holiday_flat` | LBMA-open / US-closed holidays after inception (NAV flat) |

### Calibration and the timing basis

The borrowing `spread` is calibrated so the synthetic model reproduces UGL's **cumulative** growth
over the overlap:

- Cumulative growth ratio (model / UGL) over 2008-2026: **~0.995** on the clean LBMA-calendar spot
  returns (the basis the spread was calibrated on, and what the validation test recomputes).
- Daily-return correlation: **~0.67**, annualized tracking error **~28%**.

This calibration compares the *continuous synthetic model* to UGL. The shipped dataset uses observed
UGL returns after inception, so its observed era matches UGL exactly (see the bug-fix note above).
Note: the build's reported `calibration_vs_etf_overlap` ratio (~1.33) is computed on GOLDPM's
*observed-era Price Return*, which now runs on the NYSE calendar; the LBMA-fix-vs-US-close timing
basis interacting with that calendar inflates a daily-reset continuous model. The authoritative
spread check (`test_model_tracks_ugl_over_live_overlap`) therefore recomputes on raw LBMA-calendar
returns, and the shipped series is checked directly against UGL.

Unlike the equity/Treasury leveraged datasets (~0.997 daily correlation), the daily UGL-vs-model
correlation is low — and roughly constant across all years. The cause is a **timing basis**:
`GOLDPM` is the LBMA PM fix (~10:30am ET) while UGL closes at 4pm ET, so day-over-day returns are
measured ~5.5 hours apart. A direct check confirms this: over 2008-2026, **UGL daily returns vs
2x-GLD daily returns (both at the US close) correlate at 0.997**, while **LBMA PM-fix returns vs
same-day GLD returns correlate at only 0.66**. The model logic is therefore correct; only the
clock-time of the gold base differs from UGL. Model and UGL daily volatilities match closely
(~2% each), so calibration and validation use cumulative growth and the volatility ratio rather
than daily tracking. The relatively large calibrated spread (0.93%) also absorbs gold futures
roll/storage: UGL (futures-based) ran below 2x-spot cumulatively, consistent with contango.

## Update method

`src/update_gold_2x.py` delegates to the build script's `main()`, rebuilding the full daily-reset
chain from the current `GOLDPM` CSV and freshly fetched `^IRX`/`UGL` data. Refresh `GOLDPM` first
(`src/update_gold.py`).

## Tests

`tests/validation/test_gold_2x_contract.py`:

- Scaffold paths, processed outputs, Yahoo schema.
- Coverage starts 1970-01-02; dates unique and sorted.
- Positive levels throughout; `Close == Adj Close`; `Price Return == Total Return`.
- `Total Return` recomputes from `Adj Close`.
- Segment flags present and sized; only synthetic before inception; **no synthetic fills in the
  observed era**; any holiday-flat rows (≈0 now) carry `Total Return == 0`.
- Observed segment daily returns exactly match raw UGL adjusted-close returns (against the most
  recent UGL close).
- **Regression guard:** in the observed era `Adj Close` is an exact constant multiple of raw UGL
  (`test_observed_dataset_tracks_ugl_cumulatively`) — catches any return of the holiday
  double-count or a calendar mismatch.
- Synthetic segment independently recomputed from `GOLDPM` `Price Return` + raw `^IRX` matches the
  dataset.
- Live-overlap spread calibration recomputed on **raw LBMA-calendar** spot returns vs UGL:
  cumulative ratio within 0.90-1.10; daily volatility ratio within 0.80-1.20; correlation > 0.5
  (acknowledging the timing basis).

## Caveats and future upgrades

- **Model, not history**: pre-2008 data is a model.
- **Benchmark mismatch**: UGL's benchmark is the futures-based Bloomberg Gold Subindex; the model
  underlying is LBMA PM spot. The calibrated spread absorbs the average roll/storage difference,
  but the synthetic series is not a true futures-based 2x gold history.
- **Timing basis**: daily returns are struck at the LBMA PM fix, not the US 4pm close, so daily
  alignment with UGL is limited (~0.67). For US-close-aligned daily backtests this is a real
  difference; cumulative and volatility behavior are sound.
- **Volatility decay / path dependence**: the leveraged series is not a simple 2x multiple of
  long-horizon gold returns; daily reset plus financing/fee drag compounds path-dependently.
- A future upgrade could rebuild the underlying on a US-close gold series (e.g. GLD from 2004,
  COMEX front futures earlier) to raise daily UGL fidelity, and/or add the UGL benchmark's
  futures roll explicitly.
