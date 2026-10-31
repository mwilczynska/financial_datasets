# Methodology — GLSTOCK2X (2x Daily-Reset Global Stocks, WLDU-like)

## Identifier and alias

- Dataset identifier: `global_stocks_2x`
- Backtest alias: `GLSTOCK2X`
- Type: **derived leveraged dataset** (model-derived before WLDU inception; observed WLDU returns after).

## Asset definition

`GLSTOCK2X` models a 2x daily-reset leveraged fund on the `GLSTOCK` exposure back to 1970.
Reference fund: **Leverage Shares 2x Long World Stock Daily ETF**.

- Objective/index: 2x VT (Vanguard Total World Stock ETF), through total return swaps.
- Expense ratio used: **0.75%** (net; gross not separately disclosed).
- Fund inception: 2026-03-10.
- `Close` and `Adj Close` are equal: the single series is the total-return NAV level, 100 on 1970-01-02.
- `Price Return` equals `Total Return`. `Open`, `High`, `Low` and `Volume` are blank.

## Output files

| Artifact | Path |
|---|---|
| CSV | `data/processed/global_stocks_2x.csv` |
| Parquet | `data/processed/global_stocks_2x.parquet` |
| Manifest | `sources/manifests/global_stocks_2x.yml` |
| Build metadata | `sources/manifests/global_stocks_2x_build.json` |
| Citations | `sources/citations/global_stocks_2x.md` |
| Build script | `src/build_global_stocks_2x.py` (shared logic in `src/leveraged_2x.py`) |
| Update script | `src/update_global_stocks_2x.py` |
| Tests | `tests/validation/test_leveraged_2x_contract.py` |

## Coverage

- First observation: `1970-01-02` (base level 100).
- Last observation: the latest `GLSTOCK` date. The README table and build metadata give current dates and row counts.
- Initial build snapshot (2026-10-31, data through 2026-10-27): 14,486 rows; 14,326 synthetic, 160 observed WLDU.

## Sources

- **Underlying** (`active`): `GLSTOCK` (`data/processed/global_stocks.csv`) `Total Return`. GLSTOCK global all-world equity total return; VT adjusted-close returns from 2008-06-27.
- **Financing benchmark** (`active`): Yahoo `^IRX` 13-week T-bill discount yield, forward-filled.
- **Observed ETF / calibration target**: Yahoo `WLDU` adjusted close, from 2026-03-10.
- **Parameter reference**: https://leverageshares.com/us/etfs/leverage-shares-2x-long-world-stock-daily-etf/ (accessed 2026-10-31).

## Build method

```
lev_ret = 2*u - 1*((IRX/100 + 0.0080)*days/360) - 0.0075*days/365
level_t = level_(t-1) * (1 + lev_ret_t)      # starts at 100
```

- `days` is the calendar-day gap to the previous base row (financing actual/360, expense actual/365).
- Borrowing spread **0.0080**. WLDU's ~160-day overlap cannot calibrate a spread: the bisection hit its 3% bound, with the SSO-spread model running ~4% above WLDU over 2026-03 to 2026-10 at 0.994 daily correlation. The SSO spread (same leverage, swap-financed equity) is used instead and should be revisited once WLDU has several years of history.
- From the trading day after inception the dataset uses observed WLDU adjusted-close returns. Levels compound continuously and are never rescaled.
- The calendar is the base dataset's calendar. A `-0.9999` non-positivity floor exists and does not trigger.

### Quality flags

| Flag | Segment |
|---|---|
| `model_2x_daily_reset_synthetic_from_glstock_total_return_minus_financing_and_wldu_fee` | 1970-01-02 through WLDU's first trading day (2026-03-10) |
| `observed_wldu_etf_adjusted_total_return` | WLDU trading days after its first trading day |

### Calibration

Over 160 WLDU trading days from 2026-03-10: daily correlation 0.9938, annualized tracking error 3.3%, cumulative model/WLDU ratio 1.0407.

## Update method

Each update fetches a 14-calendar-day Yahoo `WLDU` overlap and appends observed adjusted-close returns on the base calendar, like the 3x datasets. Unchanged historical rows are preserved; `--full-rebuild` reruns the builder.

## Distributions

`WLDU` is a source fund in the USD cash companions. WLDU has no complete calendar year, so its pre-fund payouts use SSO's payout model and seasonality (`payout_model_proxy`). WLDU publishes no machine-readable issuer history; Yahoo cash events are the observed source. See the [distribution methodology](methodology_distributions.md).

## Tests

`tests/validation/test_leveraged_2x_contract.py` checks schema, base calendar, positive levels, return arithmetic,
segment flags, observed returns against raw WLDU, and recomputes the synthetic segment from the base dataset and raw `^IRX`.

## Caveats

- **Model, not history**: pre-2026 data is a model. Leveraged returns are path-dependent and are not 2x long-horizon GLSTOCK returns.
- VT is already net of its own 0.06% fee, which the 2x model doubles. Before VT (2008) the base is an MSCI-anchored or Fama/French model, not VT.
- `^IRX` is a T-bill proxy for swap financing; the calibrated spread absorbs the average difference, fee waivers and base-fund fees.
- Expense ratios are current net figures. Historical fees differed, and waivers can lapse.
