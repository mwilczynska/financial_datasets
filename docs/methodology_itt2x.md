# Methodology — ITT2X (2x Daily-Reset Intermediate-Term Treasury, UST-like)

## Identifier and alias

- Dataset identifier: `intermediate_term_us_treasury_2x`
- Backtest alias: `ITT2X`
- Type: **derived leveraged dataset** (model-derived before UST inception; observed UST returns after).

## Asset definition

`ITT2X` models a 2x daily-reset leveraged fund on the `ITT` exposure back to 1970.
Reference fund: **ProShares Ultra 7-10 Year Treasury**.

- Objective/index: ICE U.S. Treasury 7-10 Year Bond Index.
- Expense ratio used: **0.95%** (net; gross 1.24%).
- Fund inception: 2010-01-19.
- `Close` and `Adj Close` are equal: the single series is the total-return NAV level, 100 on 1970-01-02.
- `Price Return` equals `Total Return`. `Open`, `High`, `Low` and `Volume` are blank.

## Output files

| Artifact | Path |
|---|---|
| CSV | `data/processed/intermediate_term_us_treasury_2x.csv` |
| Parquet | `data/processed/intermediate_term_us_treasury_2x.parquet` |
| Manifest | `sources/manifests/intermediate_term_us_treasury_2x.yml` |
| Build metadata | `sources/manifests/intermediate_term_us_treasury_2x_build.json` |
| Citations | `sources/citations/intermediate_term_us_treasury_2x.md` |
| Build script | `src/build_intermediate_term_us_treasury_2x.py` (shared logic in `src/leveraged_2x.py`) |
| Update script | `src/update_intermediate_term_us_treasury_2x.py` |
| Tests | `tests/validation/test_leveraged_2x_contract.py` |

## Sources

- **Underlying** (`active`): `ITT` (`data/processed/intermediate_term_us_treasury.csv`) `Total Return`. ITT IEF-like intermediate Treasury total return (Fed 8.5-year par model, VFITX, then IEF).
- **Financing benchmark** (`active`): Yahoo `^IRX` 13-week T-bill discount yield, forward-filled.
- **Observed ETF / calibration target**: Yahoo `UST` adjusted close, from 2010-02-02.
- **Parameter reference**: https://www.proshares.com/our-etfs/leveraged-and-inverse/ust (accessed 2026-10-31).

## Build method

```
lev_ret = 2*u - 1*((IRX/100 + -0.0033)*days/360) - 0.0095*days/365
level_t = level_(t-1) * (1 + lev_ret_t)      # starts at 100
```

- `days` is the calendar-day gap to the previous base row (financing actual/360, expense actual/365).
- Borrowing spread **-0.0033**. Calibrated to UST cumulative growth over the 2010+ overlap. The spread is negative mainly because the ITT base is net of IEF's 0.15% fee, which 2x leverage doubles; UST tracks the gross index. UST is thinly traded, which lowers its daily correlation (0.97).
- From the trading day after inception the dataset uses observed UST adjusted-close returns. Levels compound continuously and are never rescaled.
- The calendar is the base dataset's calendar. A `-0.9999` non-positivity floor exists and does not trigger.

### Quality flags

| Flag | Segment |
|---|---|
| `model_2x_daily_reset_synthetic_from_itt_total_return_minus_financing_and_ust_fee` | 1970-01-02 through UST's first trading day (2010-02-02) |
| `observed_ust_etf_adjusted_total_return` | UST trading days after its first trading day |

### Calibration

Over 4209 UST trading days from 2010-02-02: daily correlation 0.9724, annualized tracking error 3.1%, cumulative model/UST ratio 0.9994.

## Update method

Each update fetches a 14-calendar-day Yahoo `UST` overlap and appends observed adjusted-close returns on the base calendar, like the 3x datasets. Unchanged historical rows are preserved; `--full-rebuild` reruns the builder.

## Distributions

`UST` is a source fund in the USD cash companions. Issuer cash comes from the ProShares numeric-year API; pre-UST payouts use UST's own fitted model. See the [distribution methodology](methodology_distributions.md).

## Tests

`tests/validation/test_leveraged_2x_contract.py` checks schema, base calendar, positive levels, return arithmetic,
segment flags, observed returns against raw UST, and recomputes the synthetic segment from the base dataset and raw `^IRX`. It also requires cumulative model/UST growth within 2% and daily correlation above 0.95.

## Caveats

- **Model, not history**: pre-2010 data is a model. Leveraged returns are path-dependent and are not 2x long-horizon ITT returns.
- Pre-2002 underlying is a Fed par-yield model and VFITX, not the ICE index UST tracks.
- `^IRX` is a T-bill proxy for swap financing; the calibrated spread absorbs the average difference, fee waivers and base-fund fees.
- Expense ratios are current net figures. Historical fees differed, and waivers can lapse.
