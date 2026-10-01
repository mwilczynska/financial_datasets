# Independent Astra Max review: daily GSCI full history

Review date: 2026-09-30. Reviewed the [follow-up report](cmdty_daily_1970s_followup.md),
[audit script](../../scripts/research_cmdty_full_history.py),
[findings](cmdty_full_history_findings.json), and
[retrieval manifest](cmdty_full_history_retrieval_manifest.json).
Final reviewed script SHA-256:
`e61f7ac513d3814c1e769eef84ac0e6f53d6499cb0c66628aad56d7bff8c8979`.
The saved findings identify that exact script version.

Editorial update after implementation: this review records the research
snapshot and its pre-migration comparisons. The replacement is now implemented;
see [the current methodology](../methodology_cmdty.md) and
[the separate implementation review](cmdty_daily_implementation_astra_review.md).
The numerical research findings below are retained as reviewed.

**Decision: the evidence supports the direct daily GSCI research candidate.**
I found no remaining material numerical or reference-transcription error in the
reviewed snapshot. The acquired ER/TR pair is a substantially stronger basis
for the early GSCI segment than the existing sparse-anchor construction.
Production promotion remains conditional on the implementation and publication
requirements below.

I independently read the raw Excel cells, CSVs and read-only SQLite database,
calculated results without importing the audit script, and rendered and inspected
the cited PDF pages. All eight principal source hashes and byte counts match
the manifest. Independently verified results include:

| Evidence | Independent result |
|---|---|
| Preferred workbook | 14,609 unique, ordered weekday rows, 1970-01-02 through 2025-12-31; 2,607 rows in the 1970s and 5,738 in 1970-1991; all three index columns finite and positive |
| Older Duke workbook | All 120 monthly values match exactly for each of Spot, ER and TR: 360 exact 1970s matches. Across 264 months through 1991, maximum differences are 0.000590 TR, 0.000044 ER and 0.000049 Spot |
| Portfolio database | All 2,607 shared 1970s TR levels agree within 5.684e-13; all 2,606 consecutive return differences are below 1e-7 |
| Investing export | All 3,035 dates are present; maximum level difference 0.001000000000204 and common-interval log-return RMSE 0.000457725 bp |
| Quantpedia delivery | Its 3,032 overlapping observations equal the Investing export exactly |
| Published references | All 22 annual returns and all 22 dated levels were transcribed correctly and pass their published rounding tolerances |

The reference checks use Kaplan/Lummer's Appendix A,
[PDF page 13](https://www.etf.com/docs/20040913_GSCI.pdf), and
[SEC Release 34-53658, pages 29-30](https://www.sec.gov/files/rules/sro/nyse/2006/34-53658.pdf).
The largest annual discrepancy is 0.00494627 percentage points, below the strict
0.005 rounding threshold. The largest SEC level discrepancy is 0.004 index points.
These publications corroborate the same underlying index history; they are not
independently constructed benchmarks validating every daily value.

The risk comparison also reproduces. On the same 2,488 published CMDTY dates
in 1970-1979, annualized log-return volatility is **16.5019% versus 4.0108%**,
lag-one autocorrelation is **0.03467 versus 0.62680**, and maximum drawdown is
**-41.9859% versus -35.2796%**. The troughs are 1977-08-15 and 1976-11-01.
Return correlation is 0.20270 and RMSE is 101.86023 bp. The 1970-1983 volatility
comparison is 15.7435% versus 3.6968%; the 1984-1990 correlation and RMSE are
0.990330 and 13.68995 bp. These are correctly measured on common level dates,
including intervals spanning skipped dates.

Two review findings were repaired before this conclusion:

1. The manual Investing input originally had a recorded hash without an enforced
   hash check, and source comparisons were mainly descriptive. The final script
   enforces the verified Investing SHA-256, 3,035 shared dates, no missing source
   dates and the 0.001001 level-error limit. Monthly checks enforce 120 and 264
   observations, exact 1970s agreement and the stated precision limit. The saved
   findings pass these gates and the tightened published-reference tolerances.
2. Annual chart calculations originally grouped levels before taking returns,
   omitting each year's first return. They now calculate continuous matched
   returns before grouping by return end-date year. The revised output agrees
   with my independent calculation, including 22.91057% for 1973. The largest
   workbook-bar correction was 0.04534 percentage points; headline comparisons
   were unaffected.

The notebook and configuration, inspected as text only, support the stated
Bloomberg tickers, `PX_LAST` request, and previous-value fill on non-trading
weekdays. They do not authenticate the original terminal extraction. The full
weekday grid includes carried values; the 92 jointly unchanged 1970s rows are
not a reliable trading-calendar definition. Separate delivery and publication
vintage do not establish upstream independence. The portfolio database's later
discrepancies and uncertain cleaning lineage justify retaining it as corroboration.
I also reproduced the Duke weight-sheet defect: January 1970 sums to 0.95148633,
and 72 of 120 months differ from one by more than 1%. Those weights remain
unsuitable for an unqualified constituent reconstruction.

The ER/TR recommendation is sound. On 1991-01-02, source ER is 458.48 and TR is
2346.026, giving TR/ER of 5.11696475 versus published CMDTY's 2.96469388.
This establishes a discrepancy between the paired index growth paths. It does
not identify its entire cause, independently validate a stand-alone cash index,
or justify adding another return to TR. Daily ER has less external daily
corroboration than TR; its identity is supported by the companion source code
and monthly matches. Rounding-aware checks must allow tiny apparent negative
TR-minus-ER daily spreads in the early rounded observations.

Before production promotion, require:

- Document permitted use and derived publication rights. Public downloadability
  and a repository code license do not establish rights to republish the
  underlying Bloomberg/S&P observations.
- Preserve the source snapshot, index-type labels and fill qualification. Sample
  levels on the chosen calendar before calculating returns; do not discard flat
  days or select returns first. Keep the start at 1970-01-02. Label provider
  back-calculation accurately: actual index publication began May 1, 1991, so
  the January 1991 splice endpoint is still back-calculated.
- Normalize ER into `Close` and TR into `Adj Close` separately. Verify imported
  values against the source and retain the reference gates. Do not apply the old
  IRX stripping or sparse-anchor overlay to the direct series.
- If the existing boundary is retained, use GSCI through 1991-01-02 and verify
  the 1991-01-03 BCOM return from its January 2 overlap separately for each
  column. Compound from the new ER and TR endpoint levels independently.
  Assert that all later BCOM and DBC return ratios are preserved, even though
  their level scaling changes. Retain a versioned production baseline and the
  GSCI-versus-DBC methodology distinction.

The production CSV and builder still match the recorded pre-research hashes.
This review changed neither. Independent scratch calculations and PDF renders
remain under ignored `data/interim/`; the only durable file authored by this
review is this document.
