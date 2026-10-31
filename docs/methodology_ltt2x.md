# Methodology — LTT2X (2x Daily-Reset Long-Term Treasury, UBT-like)

## Identifier and alias

- Dataset identifier: `long_term_us_treasury_2x`
- Backtest alias: `LTT2X`
- Type: **derived leveraged dataset** (model-derived before UBT inception; observed UBT returns after).

## Asset definition

`LTT2X` models a 2x daily-reset leveraged fund on the `LTT` exposure back to 1970.
Reference fund: **ProShares Ultra 20+ Year Treasury**.

- Objective/index: ICE U.S. Treasury 20+ Year Bond Index.
- Expense ratio used: **0.95%** (net; gross 0.98%).
- Fund inception: 2010-01-19.
- `Close` and `Adj Close` are equal: the single series is the total-return NAV level, 100 on 1970-01-02.
- `Price Return` equals `Total Return`. `Open`, `High`, `Low` and `Volume` are blank.

## Output files

| Artifact | Path |
|---|---|
| CSV | `data/processed/long_term_us_treasury_2x.csv` |
| Parquet | `data/processed/long_term_us_treasury_2x.parquet` |
| Manifest | `sources/manifests/long_term_us_treasury_2x.yml` |
| Build metadata | `sources/manifests/long_term_us_treasury_2x_build.json` |
| Citations | `sources/citations/long_term_us_treasury_2x.md` |
| Build script | `src/build_long_term_us_treasury_2x.py` (shared logic in `src/leveraged_2x.py`) |
| Update script | `src/update_long_term_us_treasury_2x.py` |
| Tests | `tests/validation/test_leveraged_2x_contract.py` |

## Coverage

- First observation: `1970-01-02` (base level 100).
- Last observation: the latest `LTT` date. The README table and build metadata give current dates and row counts.
- Initial build snapshot (2026-10-31, data through 2026-10-27): 14,267 rows; 10,050 synthetic, 4,217 observed UBT.

## Sources

- **Underlying** (`active`): `LTT` (`data/processed/long_term_us_treasury.csv`) `Total Return`. LTT TLT-like long Treasury total return (Fed 25-year par model, VUSTX, then TLT).
- **Financing benchmark** (`active`): Yahoo `^IRX` 13-week T-bill discount yield, forward-filled.
- **Observed ETF / calibration target**: Yahoo `UBT` adjusted close, from 2010-01-21.
- **Parameter reference**: https://www.proshares.com/our-etfs/leveraged-and-inverse/ubt (accessed 2026-10-31).

## Build method

```
lev_ret = 2*u - 1*((IRX/100 + -0.0035)*days/360) - 0.0095*days/365
level_t = level_(t-1) * (1 + lev_ret_t)      # starts at 100
```

- `days` is the calendar-day gap to the previous base row (financing actual/360, expense actual/365).
- Borrowing spread **-0.0035**. Calibrated to UBT cumulative growth over the 2010+ overlap. Negative for the same reason as ITT2X: the base is net of TLT's 0.15% fee.
- From the trading day after inception the dataset uses observed UBT adjusted-close returns. Levels compound continuously and are never rescaled.
- The calendar is the base dataset's calendar. A `-0.9999` non-positivity floor exists and does not trigger.

### Quality flags

| Flag | Segment |
|---|---|
| `model_2x_daily_reset_synthetic_from_ltt_total_return_minus_financing_and_ubt_fee` | 1970-01-02 through UBT's first trading day (2010-01-21) |
| `observed_ubt_etf_adjusted_total_return` | UBT trading days after its first trading day |

### Calibration

Over 4217 UBT trading days from 2010-01-21: daily correlation 0.9848, annualized tracking error 5.2%, cumulative model/UBT ratio 1.0005.

## Update method

Each update fetches a 14-calendar-day Yahoo `UBT` overlap and appends observed adjusted-close returns on the base calendar, like the 3x datasets. Unchanged historical rows are preserved; `--full-rebuild` reruns the builder.

## Distributions

`UBT` is a source fund in the USD cash companions. Issuer cash comes from the ProShares numeric-year API; pre-UBT payouts use UBT's own fitted model. See the [distribution methodology](methodology_distributions.md).

## Tests

`tests/validation/test_leveraged_2x_contract.py` checks schema, base calendar, positive levels, return arithmetic,
segment flags, observed returns against raw UBT, and recomputes the synthetic segment from the base dataset and raw `^IRX`. It also requires cumulative model/UBT growth within 2% and daily correlation above 0.95.

## Caveats

- **Model, not history**: pre-2010 data is a model. Leveraged returns are path-dependent and are not 2x long-horizon LTT returns.
- Pre-2002 underlying is a Fed par-yield model and VUSTX with a different duration from the ICE 20+ index.
- `^IRX` is a T-bill proxy for swap financing; the calibrated spread absorbs the average difference, fee waivers and base-fund fees.
- Expense ratios are current net figures. Historical fees differed, and waivers can lapse.
