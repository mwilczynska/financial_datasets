# Methodology — LTT3X (3x Daily-Reset Long-Term Treasury, TMF-like)

## Identifier and alias

- Dataset identifier: `long_term_us_treasury_3x`
- Backtest alias: `LTT3X`
- Type: **derived leveraged dataset** (model-derived before TMF inception; observed TMF returns after).

## Asset definition

`LTT3X` models a 3x daily-reset leveraged long-term U.S. Treasury fund — Direxion Daily 20+ Year
Treasury Bull 3X Shares (`TMF`) — extended back to 1970, long before TMF's 2009-04-16 inception.

- `Close` and `Adj Close` are **equal**: a synthetic daily-reset leveraged fund has no separate
  price index, so the single series is the total-return NAV level, normalized to 100 on
  1970-01-02.
- `Price Return` equals `Total Return`.
- `Open`, `High`, `Low`, and `Volume` are blank (no reliable OHLCV for a model NAV).

This is a derived model, not observed TMF history before 2009, and must be flagged as such.

## Output files

| Artifact | Path |
|---|---|
| CSV | `data/processed/long_term_us_treasury_3x.csv` |
| Parquet | `data/processed/long_term_us_treasury_3x.parquet` |
| Interim CSV | `data/interim/long_term_us_treasury_3x.csv` |
| Manifest | `sources/manifests/long_term_us_treasury_3x.yml` |
| Build metadata | `sources/manifests/long_term_us_treasury_3x_build.json` |
| Citations | `sources/citations/long_term_us_treasury_3x.md` |
| Build script | `src/build_long_term_treasury_3x.py` |
| Update script | `src/update_long_term_treasury_3x.py` |
| Tests | `tests/validation/test_long_term_treasury_3x_contract.py` |

## Coverage

- First observation: `1970-01-02` (base level 100).
- Last observation: most recent TMF trading day from Yahoo.
- Current build: 14,174 rows, 1970-01-02 to 2026-06-15. Synthetic rows 9,857; observed TMF
  rows 4,317. TMF inception 2009-04-16.

## Sources

- **Underlying** (`active`): `LTT` (`data/processed/long_term_us_treasury.csv`) `Total Return`
  column — TLT-like long-Treasury total return (Fed yield-curve 25-year par model before VUSTX,
  then VUSTX, then TLT).
- **Financing benchmark** (`active`): Yahoo `^IRX` 13-week T-bill discount yield (percent),
  daily from 1970-01-02.
- **Observed ETF / calibration target** (`active_from_2009`): Yahoo `TMF` adjusted close.
- **Parameter reference**: Direxion TMF prospectus (3x daily ICE 20+ Year objective; ~1.06% ER).

## Build method

For each underlying trading date `t` (from `LTT`):

1. **Underlying total return** `u_t` = the `LTT` `Total Return` for `t`.
2. **Synthetic daily-reset return** (1970-01-02 through and including TMF's first trading day):

   ```
   financing_daily = (IRX_t/100 + spread) * days_t / 360
   expense_daily   = expense_ratio * days_t / 365
   lev_ret_t       = L * u_t - (L - 1) * financing_daily - expense_daily
   ```

   - `L = 3` (leverage multiple).
   - `spread = 0.0053` borrowing spread over `^IRX`, **calibrated** to the TMF overlap.
   - `expense_ratio = 0.0106` (TMF ~1.06%).
   - `IRX_t` is the `^IRX` close for `t` (forward-filled for missing dates).
   - `days_t` is the calendar-day gap to the previous trading row (financing actual/360,
     expense actual/365), capturing weekend/holiday carry.
3. **Observed TMF segment** (from the trading day after TMF inception): `lev_ret_t` = TMF
   adjusted-close daily return (`adj_t / adj_{t-1} - 1`).
4. **Level**: `level_t = level_{t-1} * (1 + lev_ret_t)`, starting at 100. Levels compound
   continuously across the synthetic→observed boundary; they are never reset or rescaled.
5. A non-positivity guard floors any single-day return at `-0.9999`. It never triggers on the
   actual data (the worst leveraged day, ≈ -18%, is well above -100%).

### Quality flags

| Flag | Segment |
|---|---|
| `model_3x_daily_reset_synthetic_from_ltt_total_return_minus_financing_and_fee` | 1970-01-02 → TMF inception day |
| `observed_tmf_etf_adjusted_total_return` | day after TMF inception → present |

### Calibration

The borrowing `spread` is the single free parameter, chosen so the synthetic model — applied
over the TMF live period — reproduces TMF's actual cumulative growth:

- Daily-return correlation: **0.997**
- Annualized tracking error: **~3.7%** (inherent to daily-reset modeling)
- Cumulative growth ratio (model / TMF) over 2009-2026: **~1.0004**

In the overlap the `LTT` underlying is TLT-based, so calibration cleanly compares model 3x vs
TMF's actual 3x of the same index family. The ~3.7% annualized tracking error reflects intraday
execution, swap/futures resets, and exact financing — not a level bias.

## Update method

`src/update_long_term_treasury_3x.py` delegates to the build script's `main()`, rebuilding the
full daily-reset chain from the current `LTT` CSV and freshly fetched `^IRX`/`TMF` data. Refresh
`LTT` first (`src/update_long_term_us_treasury.py`). A full rebuild is used because daily-reset
compounding is path-dependent and cheap to recompute.

## Tests

`tests/validation/test_long_term_treasury_3x_contract.py`:

- Scaffold paths, processed outputs, Yahoo schema.
- Coverage starts 1970-01-02; dates unique and sorted.
- Positive levels throughout; `Close == Adj Close`; `Price Return == Total Return`.
- `Total Return` recomputes from `Adj Close`.
- Segment flags present, sized, and exactly one synthetic→observed transition.
- Observed segment daily returns exactly match raw TMF adjusted-close returns.
- Synthetic segment independently recomputed from `LTT` + raw `^IRX` matches the dataset.
- Live-overlap calibration: recomputed model vs actual TMF has correlation > 0.99 and cumulative
  ratio within 0.90–1.10.

## Caveats and future upgrades

- **Model, not history**: pre-2009 data is a model. It assumes a constant borrowing spread and a
  T-bill (`^IRX`) financing proxy; TMF's real swap/futures financing rate is closer to the
  overnight rate plus a time-varying counterparty spread.
- **Duration / exposure mismatch**: TMF tracks the ICE U.S. Treasury 20+ Year Bond Index. The
  `LTT` underlying matches that only from 2002 (TLT). Before 2002 it is a 25-year constant-maturity
  par model (and VUSTX, a long-Treasury mutual fund with its own duration and fees), so the
  pre-2002 synthetic 3x series reflects a *similar but not identical* long-Treasury exposure. This
  duration mismatch is the most important caveat for this dataset.
- **Underlying inheritance**: the pre-2002 underlying inherits all `LTT` model characteristics,
  including its Fed yield-curve hierarchy and the larger early-1980s daily moves around the
  `SVENY25`/`^TYX` switch.
- **Volatility decay / path dependence**: the leveraged series is *not* a simple 3x multiple of
  long-horizon `LTT` returns; over 2009-2026 (rising rates), TMF's cumulative total return is far
  below 1.0 despite long-Treasury price-return being only modestly negative — a direct
  illustration of leverage decay. It must never be described as "3x long Treasuries over the
  period".
- **No intraday OHLC**: only a daily NAV level is modeled.
- A future upgrade could replace the `^IRX`+spread financing model with a fed-funds/OIS-based
  series and validate against UBT (2x long Treasury).
