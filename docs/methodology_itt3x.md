# Methodology — ITT3X (3x Daily-Reset Intermediate-Term Treasury, TYD-like)

## Identifier and alias

- Dataset identifier: `intermediate_term_us_treasury_3x`
- Backtest alias: `ITT3X`
- Type: **derived leveraged dataset** (model-derived before TYD inception; observed TYD returns after).

## Naming / leverage clarification

The project backlog originally labelled "UST" as the 3x intermediate-Treasury ETF. UST
(ProShares Ultra 7-10 Year Treasury) is in fact a **2x** fund. The genuine **3x** 7-10 year
Treasury ETF is **TYD** (Direxion Daily 7-10 Year Treasury Bull 3X Shares), which is the
calibration/validation target here. UST is the future target for a separate `ITT2X` (2x) dataset.

## Asset definition

`ITT3X` models a 3x daily-reset leveraged intermediate-term U.S. Treasury fund — Direxion Daily
7-10 Year Treasury Bull 3X Shares (`TYD`) — extended back to 1970, before TYD's 2009-04-16
inception.

- `Close` and `Adj Close` are **equal**: a synthetic daily-reset leveraged fund has no separate
  price index, so the single series is the total-return NAV level, normalized to 100 on
  1970-01-02.
- `Price Return` equals `Total Return`.
- `Open`, `High`, `Low`, and `Volume` are blank.

This is a derived model, not observed TYD history before 2009, and must be flagged as such.

## Output files

| Artifact | Path |
|---|---|
| CSV | `data/processed/intermediate_term_us_treasury_3x.csv` |
| Parquet | `data/processed/intermediate_term_us_treasury_3x.parquet` |
| Manifest | `sources/manifests/intermediate_term_us_treasury_3x.yml` |
| Build metadata | `sources/manifests/intermediate_term_us_treasury_3x_build.json` |
| Citations | `sources/citations/intermediate_term_us_treasury_3x.md` |
| Build script | `src/build_intermediate_treasury_3x.py` |
| Update script | `src/update_intermediate_treasury_3x.py` |
| Tests | `tests/validation/test_intermediate_treasury_3x_contract.py` |

## Coverage

- First observation: `1970-01-02` (base level 100).
- Last observation: most recent TYD trading day from Yahoo.
- Current build: 14,158 rows, 1970-01-02 to 2026-06-15. Synthetic rows 9,841; observed TYD
  rows 4,317. TYD inception 2009-04-16.

## Sources

- **Underlying** (`active`): `ITT` (`data/processed/intermediate_term_us_treasury.csv`)
  `Total Return` column — IEF-like intermediate-Treasury total return (Fed yield-curve 8.5-year
  par model before VFITX, then VFITX, then IEF).
- **Financing benchmark** (`active`): Yahoo `^IRX` 13-week T-bill discount yield (percent),
  daily from 1970-01-02.
- **Observed ETF / calibration target** (`active_from_2009`): Yahoo `TYD` adjusted close.
- **Parameter reference**: Direxion TYD prospectus (3x daily ICE 7-10 Year objective; ~1.09% ER).
- **Rejected**: ProShares UST — a 2x fund, wrong leverage for this 3x dataset.

## Build method

Identical daily-reset construction to `USLCAP3X`/`LTT3X`, with the `ITT` base:

```
financing_daily = (IRX_t/100 + spread) * days_t / 360
expense_daily   = expense_ratio * days_t / 365
lev_ret_t       = L * u_t - (L - 1) * financing_daily - expense_daily
level_t         = level_{t-1} * (1 + lev_ret_t)      # starts at 100
```

- `L = 3`; `spread = 0.0019` (calibrated to the TYD overlap); `expense_ratio = 0.0109`.
- `IRX_t` forward-filled; `days_t` is the calendar-day gap (financing actual/360, expense
  actual/365).
- Synthetic segment runs 1970-01-02 through and including TYD's first trading day; from the next
  trading day the dataset uses observed TYD adjusted-close daily returns. Levels compound
  continuously across the boundary.
- A `-0.9999` non-positivity floor is present but never triggers (intermediate Treasuries are
  low-volatility, so 3x daily moves stay well above -100%).

### Quality flags

| Flag | Segment |
|---|---|
| `model_3x_daily_reset_synthetic_from_itt_total_return_minus_financing_and_fee` | 1970-01-02 → TYD inception day |
| `observed_tyd_etf_adjusted_total_return` | day after TYD inception → present |

### Calibration and the TYD data-quality issue

The borrowing `spread` is calibrated so the synthetic model reproduces TYD's **cumulative**
growth over the live overlap:

- Cumulative growth ratio (model / TYD) over 2009-2026: **~0.9998**
- Full-overlap daily-return correlation: **~0.88**, annualized tracking error **~10%**

Unlike UPRO/TMF (~0.997 daily correlation), TYD's full-overlap daily correlation is low. A
year-by-year breakdown shows correlation of 0.92-0.99 in 2009-2013 and 0.94-0.996 in 2019-2026,
collapsing to **0.37-0.66 in 2014-2018** with many >2% daily gaps. This is the signature of TYD
being a thinly-traded, low-AUM fund with stale/illiquid Yahoo closing prices mid-decade — a TYD
market-data quality problem, not a model error. Cumulative growth is robust to such
mean-reverting stale-price noise, so it is the calibration target; daily fidelity is validated on
the clean recent era (2019+ correlation > 0.95). The low implied spread (0.19%) also partly
reflects TYD fee waivers.

## Update method

`src/update_intermediate_treasury_3x.py` delegates to the build script's `main()`, rebuilding
the full daily-reset chain from the current `ITT` CSV and freshly fetched `^IRX`/`TYD` data.
Refresh `ITT` first (`src/update_intermediate_term_us_treasury.py`).

## Tests

`tests/validation/test_intermediate_treasury_3x_contract.py`:

- Scaffold paths, processed outputs, Yahoo schema.
- Coverage starts 1970-01-02; dates unique and sorted.
- Positive levels throughout; `Close == Adj Close`; `Price Return == Total Return`.
- `Total Return` recomputes from `Adj Close`.
- Segment flags present, sized, exactly one synthetic→observed transition.
- Observed segment daily returns exactly match raw TYD adjusted-close returns.
- Synthetic segment independently recomputed from `ITT` + raw `^IRX` matches the dataset.
- Live-overlap calibration: cumulative ratio within 0.90-1.10; **clean-era (2019+) correlation
  > 0.95**; full-overlap correlation > 0.85 (documents the mid-decade TYD noise).

## Caveats and future upgrades

- **Model, not history**: pre-2009 data is a model with a constant-spread `^IRX` financing proxy.
- **TYD data noise**: the observed segment faithfully reproduces TYD's Yahoo adjusted returns,
  including the noisy 2014-2018 stale-price period; daily backtest results in that window inherit
  TYD's own market-data quality limits.
- **Exposure inheritance**: pre-2002 underlying is a Fed 8.5-year par model and VFITX, not the
  ICE 7-10 Year index TYD tracks.
- **Volatility decay / path dependence**: the leveraged series is *not* a simple 3x multiple of
  long-horizon `ITT` returns. Note the synthetic level reaches ~5,000 by 2009 — far above the
  `LTT3X` synthetic (~650) over the same period — because intermediate Treasuries were much less
  volatile than long bonds through the 1970s-80s rate spikes, so 3x daily compounding decayed far
  less. This illustrates how leverage decay depends on underlying volatility.
- A future upgrade could replace the `^IRX`+spread financing model with a fed-funds/OIS series and
  add the `ITT2X` (UST, 2x) companion.
