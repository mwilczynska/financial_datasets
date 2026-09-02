# Methodology — USLCAP3X (3x Daily-Reset U.S. Large Cap, UPRO-like)

## Identifier and alias

- Dataset identifier: `us_large_cap_3x_sp500`
- Backtest alias: `USLCAP3X`
- Type: **derived leveraged dataset** (model-derived before UPRO inception; observed UPRO returns after).

## Asset definition

`USLCAP3X` models a 3x daily-reset leveraged S&P 500 total-return fund — ProShares UltraPro
S&P500 (`UPRO`) — extended back to 1970, long before UPRO's 2009-06-25 inception.

- `Close` and `Adj Close` are **equal**: a synthetic daily-reset leveraged fund has no separate
  price index, so the single series is the total-return NAV level, normalized to 100 on
  1970-01-02.
- `Price Return` equals `Total Return` for the same reason.
- `Open`, `High`, `Low`, and `Volume` are blank (no reliable OHLCV for a model NAV).

This is a derived model, not observed UPRO history before 2009, and must be flagged as such.

## Output files

| Artifact | Path |
|---|---|
| CSV | `data/processed/us_large_cap_3x_sp500.csv` |
| Parquet | `data/processed/us_large_cap_3x_sp500.parquet` |
| Interim CSV | `data/interim/us_large_cap_3x_sp500.csv` |
| Manifest | `sources/manifests/us_large_cap_3x_sp500.yml` |
| Build metadata | `sources/manifests/us_large_cap_3x_sp500_build.json` |
| Citations | `sources/citations/us_large_cap_3x_sp500.md` |
| Build script | `src/build_us_large_cap_3x_sp500.py` |
| Update script | `src/update_us_large_cap_3x_sp500.py` |
| Tests | `tests/validation/test_us_large_cap_3x_contract.py` |

## Coverage

- First observation: `1970-01-02` (base level 100).
- Last observation: most recent UPRO trading day from Yahoo.
- Current build: 14,234 rows, 1970-01-02 to 2026-06-15. Synthetic rows 9,966; observed UPRO
  rows 4,268. UPRO inception 2009-06-25.

## Sources

- **Underlying** (`active`): `USLCAP` (`data/processed/us_large_cap_sp500.csv`) `Total Return`
  column — S&P 500 daily total return (French/CRSP large-cap before `^SP500TR`, then `^SP500TR`).
- **Financing benchmark** (`active`): Yahoo `^IRX` 13-week T-bill discount yield (percent),
  daily from 1970-01-02.
- **Observed ETF / calibration target** (`active_from_2009`): Yahoo `UPRO` adjusted close.
- **Parameter reference**: ProShares UPRO prospectus (3x daily S&P 500 objective; 0.91% ER).

## Build method

For each underlying trading date `t` (from `USLCAP`):

1. **Underlying total return** `u_t` = the `USLCAP` `Total Return` for `t`.
2. **Synthetic daily-reset return** (1970-01-02 through and including UPRO's first trading day):

   ```
   financing_daily = (IRX_t/100 + spread) * days_t / 360
   expense_daily   = expense_ratio * days_t / 365
   lev_ret_t       = L * u_t - (L - 1) * financing_daily - expense_daily
   ```

   - `L = 3` (leverage multiple).
   - `spread = 0.0065` borrowing spread over `^IRX`, **calibrated** to the UPRO overlap.
   - `expense_ratio = 0.0091` (UPRO 0.91%).
   - `IRX_t` is the `^IRX` close for `t` (forward-filled for missing dates).
   - `days_t` is the calendar-day gap to the previous trading row, so weekend/holiday financing
     and expense carry are captured (financing actual/360, expense actual/365).
3. **Observed UPRO segment** (from the trading day after UPRO inception): `lev_ret_t` = UPRO
   adjusted-close daily return (`adj_t / adj_{t-1} - 1`).
4. **Level**: `level_t = level_{t-1} * (1 + lev_ret_t)`, starting at 100. Levels compound
   continuously across the synthetic→observed boundary; they are never reset or rescaled.
5. A non-positivity guard floors any single-day return at `-0.9999`. It never triggers on the
   actual data (the worst day, 1987-10-19, is ≈ -57% leveraged, well above -100%).

### Quality flags

| Flag | Segment |
|---|---|
| `model_3x_daily_reset_synthetic_from_uslcap_total_return_minus_financing_and_fee` | 1970-01-02 → UPRO inception day |
| `observed_upro_etf_adjusted_total_return` | day after UPRO inception → present |

### Calibration

The borrowing `spread` is the single free parameter. It was chosen so the synthetic model —
applied over the UPRO live period — reproduces UPRO's actual cumulative growth:

- Daily-return correlation: **0.998**
- Annualized tracking error: **~3.2%** (inherent to daily-reset modeling)
- Mean daily return difference: **~1e-5**
- Cumulative growth ratio (model / UPRO) over 2009-2026: **~1.0000**

The ~3.2% annualized tracking error reflects intrinsic daily-reset/path differences between a
modeled NAV and the real fund (intraday execution, swap resets, securities lending, exact
financing rate), not a level bias.

## Update method

`src/update_us_large_cap_3x_sp500.py` delegates to the build script's `main()`, rebuilding the
full daily-reset chain from the current `USLCAP` CSV and freshly fetched `^IRX`/`UPRO` data.
Refresh `USLCAP` first (`src/update_us_large_cap_sp500.py`) so the derived series picks up the
latest underlying total returns. A full rebuild is used because daily-reset compounding is
path-dependent and cheap to recompute.

## Tests

`tests/validation/test_us_large_cap_3x_contract.py`:

- Scaffold paths, processed outputs, Yahoo schema.
- Coverage starts 1970-01-02; dates unique and sorted.
- Positive levels throughout; `Close == Adj Close`; `Price Return == Total Return`.
- `Total Return` recomputes from `Adj Close`.
- Segment flags present, sized, and exactly one synthetic→observed transition.
- Observed segment daily returns exactly match raw UPRO adjusted-close returns.
- Synthetic segment independently recomputed from `USLCAP` + raw `^IRX` matches the dataset
  (returns and compounded level).
- Live-overlap calibration: recomputed model vs actual UPRO has correlation > 0.99 and
  cumulative ratio within 0.90–1.10.

## Caveats and future upgrades

- **Model, not history**: pre-2009 data is a model. It assumes a constant borrowing spread and a
  T-bill (`^IRX`) financing proxy; the real swap financing rate is closer to the overnight rate
  plus a time-varying counterparty spread.
- **Underlying inheritance**: pre-1988 underlying is a CRSP large-cap total-return proxy, not
  official S&P 500 total return.
- **Volatility decay / path dependence**: the leveraged series is *not* a simple 3x multiple of
  long-horizon `USLCAP` returns; daily reset plus financing/fee drag produces large path-dependent
  divergence over time. It must never be described as "3x the S&P 500 over the period".
- **No intraday OHLC**: only a daily NAV level is modeled.
- A future upgrade could replace the `^IRX`+spread financing model with a fed-funds/OIS-based
  financing series and a time-varying spread, and validate against SSO (2x) and other ProShares
  S&P 500 leverage tiers.
