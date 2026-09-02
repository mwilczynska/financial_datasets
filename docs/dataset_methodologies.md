# Dataset Methodologies

This file is an index. Each dataset has its own methodology file in `docs/`.

## Datasets

| Alias | Asset | File | Status |
|---|---|---|---|
| `USLCAP` | U.S. Large-Cap Equity / S&P 500 | [methodology_uslcap.md](methodology_uslcap.md) | complete |
| `GOLDPM` | Gold — GLD-tracking (LBMA PM spot extended to 1970) | [methodology_goldpm.md](methodology_goldpm.md) | production built; Adj Close tracks GLD incl. fees, observed GLD from 2004 |
| `ITT` | Intermediate-Term U.S. Treasury (IEF-like, 7-10 yr) | [methodology_itt.md](methodology_itt.md) | complete model-derived |
| `LTT` | Long-Term U.S. Treasury (TLT-like, 20+ yr) | [methodology_ltt.md](methodology_ltt.md) | complete model-derived |
| `STT` | Short-Term U.S. Treasury (SHY-like, 1-3 yr) | [methodology_stt.md](methodology_stt.md) | complete model-derived |
| `CMDTY` | Broad Commodities (DBC-like, diversified futures total return) | [methodology_cmdty.md](methodology_cmdty.md) | complete model-derived; covers 1970-present (1970-1991 anchored to S&P GSCI Total Return — roll yield + collateral; 1970-1983 smoothed daily, 1984-1991 de-smoothed onto ^SPGSCI spot shape) |
| `USLCAP3X` | 3x Daily-Reset U.S. Large Cap (UPRO-like) | [methodology_uslcap3x.md](methodology_uslcap3x.md) | complete model-derived; derived 3x daily-reset model from USLCAP (1970-2009), observed UPRO returns from 2009 |
| `LTT3X` | 3x Daily-Reset Long-Term Treasury (TMF-like) | [methodology_ltt3x.md](methodology_ltt3x.md) | complete model-derived; derived 3x daily-reset model from LTT (1970-2009), observed TMF returns from 2009 |
| `ITT3X` | 3x Daily-Reset Intermediate-Term Treasury (TYD-like) | [methodology_itt3x.md](methodology_itt3x.md) | complete model-derived; derived 3x daily-reset model from ITT (1970-2009), observed TYD returns from 2009 |
| `GOLD2X` | 2x Daily-Reset Gold (UGL-like) | [methodology_gold2x.md](methodology_gold2x.md) | complete model-derived; 2x daily-reset from GOLDPM Price Return (1970-2008), observed UGL from 2008; holiday double-count fixed 2026-06-20 |
| `CPI` | U.S. CPI-U Inflation Index | [methodology_cpi.md](methodology_cpi.md) | complete model-derived daily deflator from monthly BLS CPI-U |
| `GLSTOCK` | Global All-World Stocks | [methodology_glstock.md](methodology_glstock.md) | complete model-derived public-source proxy; USLCAP/MSCI annual model -> French developed daily -> VT |
| `GLBOND` | Unhedged Global Bonds | [methodology_glbond.md](methodology_glbond.md) | complete model-derived public-source proxy; JST-anchored daily FX (BIS) + daily bond TR for US/JP/UK (in-repo Treasury, MoF, BoE) + OECD MEI monthly yields elsewhere -> BND/BWX unhedged daily blend |
| `GLSTBOND` | Unhedged Global Short-Term (1-3yr) Govt Bonds | [methodology_glstbond.md](methodology_glstbond.md) | complete model-derived public-source proxy; direct (no JST overlay) daily FX (BIS) + daily 2yr US/JP/UK (STT, MoF 2yr from 1974, BoE 2yr) + OECD 2yr-interpolated yields elsewhere -> GDP-weighted SHY+ISHG/BWZ blend; modeled fees (Close gross, Adj Close net) |

## Required Methodology Template

Every new dataset methodology file must cover:

- Dataset identifier and backtest alias.
- Asset definition and what `Close`, `Adj Close`, `Price Return`, and `Total Return` represent.
- Output files table (CSV, Parquet, manifest, citations, build script, update script, test file).
- Coverage start date and notes on the first observation.
- Production sources, validation sources, and rejected or limited sources.
- Build method: step-by-step construction including source splices, rebasing, quality flags, and assumptions.
- Update method: how the dataset is refreshed incrementally or rebuilt.
- Tests: what the validation tests cover and which assertions are key.
- Caveats: what the dataset is not, and what a future upgrade would require.
