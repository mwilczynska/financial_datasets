# 2x Gold (UGL-like) Source Notes

Accessed: 2026-06-17; revised 2026-06-20 (holiday double-count fix; re-based to Price Return).

## Holiday double-count fix (2026-06-20)

The earlier build filled ~98 US-market holidays (LBMA open, UGL closed) with a synthetic 2x-gold
day **and** let UGL's reopen close-to-close return span the same holiday — counting the holiday's
gold move twice. Those fills compounded an extra 1.29× factor, pushing GOLD2X **+33.8% (+1.89%/yr)
above UGL** over 2008-2026 (concentrated in the 2009-2012 gold bull run). The fix holds holiday
rows flat (Total Return 0); the move is captured once at UGL's next close. Over the observed era
the dataset NAV is now an exact constant multiple of UGL (CAGR gap 0.0000%), guarded by
`test_observed_dataset_tracks_ugl_cumulatively`.

## GOLDPM base dataset (gold)

- Path: `data/processed/gold.csv`
- Use: underlying daily return (`u`) for the 2x daily-reset model.
- Finding: the **`Price Return`** column is the pure LBMA Gold Price PM spot return, covering
  1970-01-02 to present. Price Return (not Total Return) is used because GOLDPM was redefined to
  track GLD: its `Total Return`/`Adj Close` now carry GLD's 0.40% expense drag. Building the 2x
  fund on the pure-spot price return keeps fund fees counted once.
- Caveat: this is the LBMA PM fix (~10:30am ET / 3pm London), a spot fixing, not a futures or ETF
  return. See the timing note below.

## Yahoo Finance Chart API — ^IRX (financing benchmark)

- Endpoint: https://query1.finance.yahoo.com/v8/finance/chart/%5EIRX
- Use: financing-rate benchmark for the borrowed (1x) exposure of the 2x fund.
- Finding: 13-week T-bill annualized discount yield (percent), daily from 1970-01-02.
- Caveat: a proxy for the fund's swap/futures financing rate; a calibrated borrowing spread is
  added on top.

## Yahoo Finance Chart API — UGL (observed ETF + calibration target)

- Endpoint: https://query1.finance.yahoo.com/v8/finance/chart/UGL
- Use: observed adjusted-close total returns from inception, and the calibration target.
- Finding: Yahoo returns UGL daily adjusted history from 2008-12-03 (ProShares Ultra Gold
  inception). The calibrated model matches UGL's cumulative growth within ~0.07% over the overlap.
  However, the **daily UGL-vs-model correlation is only ~0.67** (annualized tracking error ~28%),
  roughly constant across all years.
- Caveat: UGL adjusted close is the production source from inception; the modest daily correlation
  is a timing basis (below), not a data-quality problem.

## Yahoo Finance Chart API — GLD (timing-basis cross-check)

- Endpoint: https://query1.finance.yahoo.com/v8/finance/chart/GLD
- Use: a US-close gold ETF used only to diagnose the UGL-vs-model timing basis (not in the build).
- Finding: over 2008-2026, **UGL daily returns vs 2x-GLD daily returns correlate at 0.997** (both
  struck at the 4pm ET US close), confirming the 2x daily-reset model logic is correct. By
  contrast, **LBMA PM-fix returns vs same-day GLD returns correlate at only 0.658**. The ~0.66
  figure is purely the ~5.5-hour clock offset between the LBMA PM fix (~10:30am ET) and the US
  4pm close. This is why the GOLDPM-based model correlates with UGL at only ~0.67 day-to-day even
  though it is the right gold exposure. Daily volatilities of the model and UGL match closely
  (~2% each), so calibration uses cumulative growth and the volatility ratio rather than daily
  tracking.

## ProShares UGL prospectus / fund page

- URL: https://www.proshares.com/our-etfs/leveraged-and-inverse/ugl
- Use: parameter reference.
- Finding: UGL seeks daily investment results, before fees and expenses, of 2x the daily
  performance of the Bloomberg Gold Subindex; the fund's annual expense ratio is 0.95%.
- Caveat: the benchmark is futures-based (COMEX gold), whereas the model underlying is LBMA PM
  spot. The calibrated spread (0.93%, larger than the Treasury-fund spreads) absorbs the average
  futures roll/storage and spot-vs-futures difference; UGL ran below 2x-spot cumulatively,
  consistent with gold's typical contango.
