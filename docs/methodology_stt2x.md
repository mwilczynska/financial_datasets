# Methodology — STT2X (2x Daily-Reset Short-Term Treasury, modeled with UST-style fees)

## Identifier and alias

- Dataset identifier: `short_term_us_treasury_2x`
- Backtest alias: `STT2X`
- Type: **derived leveraged dataset** (model-derived on every row).

## Asset definition

`STT2X` models a 2x daily-reset leveraged fund on the `STT` exposure back to 1970.
Reference fund: **none (modeled with ProShares UST parameters)**.

- Objective/index: none: no 2x 1-3 year Treasury fund exists.
- Expense ratio used: **0.95%** (net; gross 1.24% (UST)).
- No fund exists. Fee and financing spread are ProShares UST parameters, the nearest current 2x Treasury fund.
- `Close` and `Adj Close` are equal: the single series is the total-return NAV level, 100 on 1970-01-02.
- `Price Return` equals `Total Return`. `Open`, `High`, `Low` and `Volume` are blank.

## Output files

| Artifact | Path |
|---|---|
| CSV | `data/processed/short_term_us_treasury_2x.csv` |
| Parquet | `data/processed/short_term_us_treasury_2x.parquet` |
| Manifest | `sources/manifests/short_term_us_treasury_2x.yml` |
| Build metadata | `sources/manifests/short_term_us_treasury_2x_build.json` |
| Citations | `sources/citations/short_term_us_treasury_2x.md` |
| Build script | `src/build_short_term_us_treasury_2x.py` (shared logic in `src/leveraged_2x.py`) |
| Update script | `src/update_short_term_us_treasury_2x.py` |
| Tests | `tests/validation/test_leveraged_2x_contract.py` |

## Coverage

- First observation: `1970-01-02` (base level 100).
- Last observation: the latest `STT` date. The README table and build metadata give current dates and row counts.
- Initial build snapshot (2026-10-31, data through 2026-10-27): 14,251 rows; 14,251 synthetic, 0 observed.

## Sources

- **Underlying** (`active`): `STT` (`data/processed/short_term_us_treasury.csv`) `Total Return`. STT SHY-like short Treasury total return (Fed curve model, VFISX, then SHY).
- **Financing benchmark** (`active`): Yahoo `^IRX` 13-week T-bill discount yield, forward-filled.
- **Observed ETF**: none. No 2x fund on this exposure exists (checked 2026-10-31: ProShares, Direxion, other US issuers and UCITS listings).
- **Parameter reference**: https://www.proshares.com/our-etfs/leveraged-and-inverse/ust (accessed 2026-10-31).

## Build method

```
lev_ret = 2*u - 1*((IRX/100 + -0.0033)*days/360) - 0.0095*days/365
level_t = level_(t-1) * (1 + lev_ret_t)      # starts at 100
```

- `days` is the calendar-day gap to the previous base row (financing actual/360, expense actual/365).
- Borrowing spread **-0.0033**. No fund to calibrate against. Uses the UST spread. STT's base deducts SHY's 0.15% fee from 2002, close to IEF's, so the offset is similar.
- No observed segment; every row is model-derived.
- The calendar is the base dataset's calendar. A `-0.9999` non-positivity floor exists and does not trigger.

### Quality flags

| Flag | Segment |
|---|---|
| `model_2x_daily_reset_synthetic_from_stt_total_return_minus_financing_and_proshares_treasury_style_fee` | 1970-01-02 onward (every row) |

### Calibration

No live fund; no overlap diagnostic.

## Update method

Each update extends the daily-reset model over the refreshed STT tail with a 14-calendar-day Yahoo `^IRX` overlap. The publication gate recomputes recent rows from the base dataset and the current `^IRX` response. Unchanged historical rows are preserved; `--full-rebuild` reruns the builder.

## Distributions

Cash companions use UST's payout model as a disclosed proxy on every date, flagged as modeled. See the [distribution methodology](methodology_distributions.md).

## Tests

`tests/validation/test_leveraged_2x_contract.py` checks schema, base calendar, positive levels, return arithmetic,
segment flags, UST parameter reuse, and recomputes the synthetic segment from the base dataset and raw `^IRX`.

## Caveats

- **Model, not history**: every row is a model. Leveraged returns are path-dependent and are not 2x long-horizon STT returns.
- Entirely model-derived. With low-volatility short Treasuries, fees and financing consume much of the leveraged carry; the series can underperform STT itself for long stretches.
- `^IRX` is a T-bill proxy for swap financing; the calibrated spread absorbs the average difference, fee waivers and base-fund fees.
- Expense ratios are current net figures. Historical fees differed, and waivers can lapse.
