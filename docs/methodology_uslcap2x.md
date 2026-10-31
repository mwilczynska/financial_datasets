# Methodology — USLCAP2X (2x Daily-Reset U.S. Large Cap, SSO-like)

## Identifier and alias

- Dataset identifier: `us_large_cap_2x_sp500`
- Backtest alias: `USLCAP2X`
- Type: **derived leveraged dataset** (model-derived before SSO inception; observed SSO returns after).

## Asset definition

`USLCAP2X` models a 2x daily-reset leveraged fund on the `USLCAP` exposure back to 1970.
Reference fund: **ProShares Ultra S&P500**.

- Objective/index: S&P 500.
- Expense ratio used: **0.84%** (net; gross 0.88%).
- Fund inception: 2006-06-19.
- `Close` and `Adj Close` are equal: the single series is the total-return NAV level, 100 on 1970-01-02.
- `Price Return` equals `Total Return`. `Open`, `High`, `Low` and `Volume` are blank.

## Output files

| Artifact | Path |
|---|---|
| CSV | `data/processed/us_large_cap_2x_sp500.csv` |
| Parquet | `data/processed/us_large_cap_2x_sp500.parquet` |
| Manifest | `sources/manifests/us_large_cap_2x_sp500.yml` |
| Build metadata | `sources/manifests/us_large_cap_2x_sp500_build.json` |
| Citations | `sources/citations/us_large_cap_2x_sp500.md` |
| Build script | `src/build_us_large_cap_2x_sp500.py` (shared logic in `src/leveraged_2x.py`) |
| Update script | `src/update_us_large_cap_2x_sp500.py` |
| Tests | `tests/validation/test_leveraged_2x_contract.py` |

## Coverage

- First observation: `1970-01-02` (base level 100).
- Last observation: the latest `USLCAP` date. The README table and build metadata give current dates and row counts.
- Initial build snapshot (2026-10-31, data through 2026-10-27): 14,327 rows; 9,208 synthetic, 5,119 observed SSO.

## Sources

- **Underlying** (`active`): `USLCAP` (`data/processed/us_large_cap_sp500.csv`) `Total Return`. S&P 500 daily total return (French/CRSP large cap before ^SP500TR, then ^SP500TR).
- **Financing benchmark** (`active`): Yahoo `^IRX` 13-week T-bill discount yield, forward-filled.
- **Observed ETF / calibration target**: Yahoo `SSO` adjusted close, from 2006-06-21.
- **Parameter reference**: https://www.proshares.com/our-etfs/leveraged-and-inverse/sso (accessed 2026-10-31).

## Build method

```
lev_ret = 2*u - 1*((IRX/100 + 0.0080)*days/360) - 0.0084*days/365
level_t = level_(t-1) * (1 + lev_ret_t)      # starts at 100
```

- `days` is the calendar-day gap to the previous base row (financing actual/360, expense actual/365).
- Borrowing spread **0.0080**. Calibrated to SSO cumulative growth over the 2006+ overlap. The SSO fee waiver runs to 2027-09-30.
- From the trading day after inception the dataset uses observed SSO adjusted-close returns. Levels compound continuously and are never rescaled.
- The calendar is the base dataset's calendar. A `-0.9999` non-positivity floor exists and does not trigger.

### Quality flags

| Flag | Segment |
|---|---|
| `model_2x_daily_reset_synthetic_from_uslcap_total_return_minus_financing_and_sso_fee` | 1970-01-02 through SSO's first trading day (2006-06-21) |
| `observed_sso_etf_adjusted_total_return` | SSO trading days after its first trading day |

### Calibration

Over 5119 SSO trading days from 2006-06-21: daily correlation 0.9954, annualized tracking error 3.8%, cumulative model/SSO ratio 0.9990.

## Update method

Each update fetches a 14-calendar-day Yahoo `SSO` overlap and appends observed adjusted-close returns on the base calendar, like the 3x datasets. Unchanged historical rows are preserved; `--full-rebuild` reruns the builder.

## Distributions

`SSO` is a source fund in the USD cash companions. Issuer cash comes from the ProShares numeric-year API; pre-SSO payouts use SSO's own fitted model. See the [distribution methodology](methodology_distributions.md).

## Tests

`tests/validation/test_leveraged_2x_contract.py` checks schema, base calendar, positive levels, return arithmetic,
segment flags, observed returns against raw SSO, and recomputes the synthetic segment from the base dataset and raw `^IRX`. It also requires cumulative model/SSO growth within 2% and daily correlation above 0.95.

## Caveats

- **Model, not history**: pre-2006 data is a model. Leveraged returns are path-dependent and are not 2x long-horizon USLCAP returns.
- Pre-1988 underlying is a CRSP large-cap proxy, not the S&P 500 itself.
- `^IRX` is a T-bill proxy for swap financing; the calibrated spread absorbs the average difference, fee waivers and base-fund fees.
- Expense ratios are current net figures. Historical fees differed, and waivers can lapse.
