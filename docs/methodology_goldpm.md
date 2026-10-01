# GOLDPM — Gold (GLD price and total return, modeled history to 1970)

Dataset identifier: `gold`; compatibility alias: `GOLDPM`.

On 2026-09-30 the entire observed price segment switched to GLD from its earliest
available daily quote, **2004-11-18**, replacing live LBMA PM dependence. The alias
is retained for consumers; modern prices are no longer London PM fixings.

## Columns and sources

| Segment | Calendar | Close / Price Return | Adj Close / Total Return |
|---|---|---|---|
| 1970-01-02–2004-11-17 | Historical LBMA/London | Published LBMA PM USD/oz and spot returns | Published spot model less 0.40% annual GLD expense accrual, actual/365 |
| 2004-11-18 onward | GLD/NYSE trading dates | Constant multiple of Yahoo GLD market close and its daily returns | Constant multiple of Yahoo GLD adjusted close and its daily returns |

Observed levels are **indices, not USD-per-ounce quotes**. GLD's prices already
include fund expenses; no additional GLD fee is deducted. OHLC fields other than
Close, and Volume, remain blank because outputs are stitched indices.

## Stitch at GLD's first available quote

The downloaded full chart starts on 2004-11-18. Missing that quote is an error;
the splice must not move to a later date. With `C0` and `A0` the final modeled
levels on 2004-11-17, and `P0` and `Q0` the first GLD close and adjusted close:

```
Close[t]     = C0 * GLD_close[t] / P0
Adj Close[t] = A0 * GLD_adjusted_close[t] / Q0
```

Both first GLD levels equal the preceding modeled levels. Splice-date returns
are zero: no cross-instrument return from a London quote into the initial ETF
quote can be observed. From GLD's second quote onward, returns follow GLD exactly.
The previous adjusted-return series used this same first-quote anchor.

Pre-GLD rows remain unchanged. All observed dates follow GLD; UK holidays need
no LBMA fallback. `Close` retains historical spot units only before GLD; the
modern column has the documented ETF-index definition.

## Builds and daily updates

`python src/build_gold.py --end-date YYYY-MM-DD --root .` preserves the published
pre-GLD model from `data/processed/gold.csv`, retrieves full GLD history, and
rebuilds the entire observed segment. The committed dataset supplies the model
in a fresh checkout. LBMA is not requested.

`--refresh-historical-sources` explicitly requests LBMA to reconstruct the model;
that optional operation still requires historical source access. The failed
2026-09-30 endpoint is not bypassed or silently substituted.

`python src/update_gold.py --end-date YYYY-MM-DD` checks a recent Yahoo overlap
and compounds GLD price and adjusted returns. The publication gate checks both
returns against current GLD quotes. Neither ordinary updating nor the gate uses
LBMA. CSV, Parquet, and build metadata are kept together; source hashes, coverage,
the pre-GLD model hash, and the first-quote splice are recorded in metadata.

Outputs: `data/processed/gold.csv`, `gold.parquet`. Definitions:
`sources/manifests/gold.yml`; citations: `sources/citations/gold.md`.

Quality flags:

- `model_gld_tracking_lbma_pm_spot_minus_gld_expense`: historical model.
- `observed_gld_etf_price_and_adjusted_total_return`: both indices from GLD.

## GOLD2X dependency

GLD returns include its expenses and must not replace the fee-free underlying
of the historical leveraged model. GOLD2X retains pre-GLD spot returns plus
`sources/derived/gold_2x_historical_spot_returns.csv` for 2004-11-18–2008-12-03.
These 1,018 frozen observations come from the previously published GOLDPM data,
including its GLD-stepped UK holidays. They are not independent daily fixings.
Existing synthetic leveraged history and observed UGL history are preserved.

## Validation and limitations

Checks cover the exact inception date, continuous splice, both GLD scales,
trading dates, arithmetic, positive levels, CSV/Parquet agreement, unchanged
historical modeling, update repeatability, and unavailable-source protection.
Historical raw LBMA comparisons apply only to the model segment.

Pre-2004 is modeled GLD exposure. GLD's US-close timing and premium/discount can
differ from spot fixings. A constant multiple of GLD does not recover USD/oz,
because gold represented per share declines with expenses. Yahoo access and
redistribution terms remain an unresolved data-rights constraint; a client
library licence does not grant rights to the data.
