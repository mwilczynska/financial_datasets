# USD cash distributions: feasibility and proposed data contract

Research date: 2026-10-28. Published data inspected through 2026-10-23.
Status: original investigation and implementation recommendation. The subsequent
implementation and published companion contract are documented in
[USD cash distributions](../methodology_distributions.md).

## Scope and conclusion

The repository can support USD cash distributions alongside its existing total
returns. Modern distributions should come from the **same funds used by the
current daily updater**, rather than substitute ETFs. Earlier synthetic periods
need separately flagged distribution models. Future distributions are model
outputs, even where historical distributions are observed.

Tax calculations, investor residence, account treatment and currency conversion
belong to the consuming application. Cash distributions and taxable allocations
are different quantities; this proposed dataset describes cash payments.

All 14 processed CSVs were inspected. None contains an explicit dividend,
distribution, coupon-payment, ex-date or payment-date column. Some retain useful
income information in the difference between their return columns; others
deliberately use both columns for total returns, expenses or collateral returns.
Consequently, a universal `Total Return - Price Return` extraction is invalid.

The current source map is `ASSETS` in `src/incremental_update.py`. Its fund
symbols are SHY, IEF, TLT, VT, BND, BWX, ISHG, BWZ, UPRO, TYD, TMF, GLD, UGL
and DBC. USLCAP uses `^GSPC` and `^SP500TR`, with no fund source. CPI is a deflator.

## Prospectus verification: GLD and UGL

**GLD / GOLDPM.** The prospectus currently linked from the issuer's U.S. GLD page
is dated October 4, 2022. Its **Distributions** section, printed page 31
(PDF page 35), permits shareholder distributions in two circumstances:

- The trustee and sponsor determine that cash exceeds the next 12 months'
  expected expenses and that the excess exceeds USD 0.01 per outstanding share.
- The trust liquidates, after liabilities and required reserves are satisfied.

The issuer explains that GLD generates no income and sells gold to meet expenses.
Its available Yahoo price history, 2004-11-18 through 2026-10-23, contains no cash
distribution events. A zero **routine cash payout** baseline is supported;
exceptional distributions must remain representable.

Sources: [issuer GLD page](https://www.spdrgoldshares.com/usa/gld/),
[issuer-linked prospectus, Distributions, p. 31](https://files.spdrgoldshares.com/spdr-cms/2025-10/GLD_Prospectus_10042022_as_filed.pdf#page=35),
[State Street GLD description](https://www.ssga.com/us/en/individual/etfs/spdr-gold-shares-gld).

**UGL / GOLD2X.** The ProShares Trust II prospectus filed in March 2026 explicitly
includes ProShares Ultra Gold. Its **Distributions** section states:
“The Sponsor does not expect to make distributions.” The issuer's UGL product page
separately states that the fund has made no distributions. Yahoo returned no cash
distribution events for 2008-12-03 through 2026-10-23, although it did return a
split event. A zero cash-payout baseline is therefore supported by policy and
observed history. The policy is an expectation, so retain an event-ingestion path
for future changes. Fund earnings or interest earned inside UGL are not thereby
cash paid to its shareholders.

Sources: [ProShares Trust II prospectus, Distributions](https://www.sec.gov/Archives/edgar/data/1415311/000119312526126553/d86378d424b3.htm),
[UGL issuer page, Distributions](https://www.proshares.com/our-etfs/leveraged-and-inverse/ugl).

These findings establish policy and corroborate the observed zero-event histories.
They do not convert missing vendor data into proof that distributions are
impossible. Before-fund periods would be modeled zero payouts under these fund
policies, rather than observations of funds that did not yet exist.

## What each dataset supports

| Asset | Current daily source | Existing distribution information | Recommended construction |
|---|---|---|---|
| USLCAP | `^GSPC` + `^SP500TR` | Matching S&P price/TR concepts from 1988-01-05, but material historical data inconsistencies exist. Before that, price is S&P and TR is a different CRSP/French portfolio. | Derive index dividend contribution only from validated matching observations. Model unresolved and early periods; there is no current fund payout schedule to recover. |
| STT | SHY | Separate price/TR throughout; early difference is modeled daily coupon carry. SHY returns begin 2002-07-31. | Fetch SHY cash events for the fund period. For older periods use existing income/carry information with a SHY-like payout model. |
| ITT | IEF | Same distinction; IEF returns begin 2002-07-31. | Fetch IEF events; model earlier payouts from income/carry using IEF's payout behavior. |
| LTT | TLT | Same distinction; TLT returns begin 2002-07-31. | Fetch TLT events; model earlier payouts from income/carry using TLT's payout behavior. |
| GLSTOCK | VT | `Close == Adj Close`; both returns already include distributions. VT returns begin 2008-06-27. | Add VT prices and cash events. Earlier distributions require an equity-income model calibrated to VT, with explicit limits when applied to older proxy regimes. |
| GLBOND | 45% BND + 55% BWX | Both columns are the same TR series. Observed blend begins 2007-10-12. | Combine BND/BWX distribution rates using the existing daily weights and calendar rules. Model the early government-bond basket's income separately. |
| GLSTBOND | SHY + ISHG + BWZ, GDP-weighted | Price/TR columns represent gross/net **total return**. Their gap is fees. First ETF-blend row in the inspected output is 2009-02-02. | Combine component distribution rates with the actual date-specific builder weights and missing-leg rules. Model early coupon income. |
| USLCAP3X | UPRO | Both columns contain UPRO total returns after 2009-06-25. | Fetch UPRO cash events and prices; calibrate earlier payout assumptions from UPRO itself. |
| ITT3X | TYD | Both columns contain TYD total returns after 2009-04-16. | Fetch TYD cash events and prices; model earlier payouts separately. |
| LTT3X | TMF | Both columns contain TMF total returns after 2009-04-16. | Fetch TMF cash events and prices; model earlier payouts separately. |
| GOLDPM | GLD | Pre-GLD gap is modeled expense drag; observed GLD has no cash distributions in the inspected history. | Zero routine payout baseline, preserving exceptional-event support. |
| GOLD2X | UGL | Both columns contain total returns; source history and issuer report no cash payouts. | Zero baseline under the verified current policy; preserve exceptional-event support. |
| CMDTY | DBC | DBC price/TR split from 2006-02-07; earlier ER/TR split describes collateral income. | Fetch DBC cash events. Model any earlier DBC-like payouts explicitly; collateral accrual is not a shareholder payment. |
| CPI | BLS/FRED CPI | Inflation measure. | Distribution field is not applicable. |

For STT/ITT/LTT, older mutual-fund proxy rows still describe their historical
source chains, but the proposed modeled distribution layer targets the funds
used today. This recommendation does not add another fund family or replace
the return sources.

Leveraged distributions must not be computed as two or three times an
unleveraged asset's dividend or coupon yield. The funds' holdings, derivatives,
financing, collateral income and realized gains determine their payouts.
ProShares explicitly states that its distributions can differ from those of
its benchmarks. [UPRO issuer explanation](https://www.proshares.com/our-etfs/leveraged-and-inverse/upro)

## Source acquisition was tested

A read-only probe requested the full available chart history for all 14 current
funds and both S&P indices, ending on the current published endpoint,
2026-10-23. It used the existing Yahoo chart route with
`events=div,splits,capitalGains` instead of `events=history`.

All 16 requests succeeded. All source currencies were USD. Twelve funds returned
cash events; GLD and UGL returned none. The vendor supplied 1,672 entries under
`dividends` across the 12 paying funds. This verifies acquisition feasibility,
not completeness or issuer-level accuracy of every entry.

| Current fund | First available quote in probe | Vendor cash-event count through 2026-10-23 |
|---|---|---:|
| SHY | 2002-07-30 | 290 |
| IEF | 2002-07-30 | 291 |
| TLT | 2002-07-30 | 289 |
| VT | 2008-06-26 | 61 |
| BND | 2007-04-10 | 232 |
| BWX | 2007-10-11 | 171 |
| ISHG | 2009-01-28 | 75 |
| BWZ | 2009-01-30 | 117 |
| UPRO | 2009-06-25 | 47 |
| TYD | 2009-04-16 | 40 |
| TMF | 2009-04-16 | 50 |
| GLD | 2004-11-18 | 0 |
| UGL | 2008-12-03 | 0 |
| DBC | 2006-02-06 | 9 |

No separate `capitalGains` collections were returned. This is not evidence of
no capital-gain cash payments: TYD's 2020-12-10 payment appears in Yahoo's
`dividends` collection, while the OCC corporate-action notice identifies it as
a short-term capital-gains distribution. Cash records must cover all cash
distribution types without assuming the vendor field establishes their nature.
[OCC TYD notice](https://infomemo.theocc.com/infomemos?number=47980)

The current updater requests no event collections and its `chart_rows` parser
only retains quotes/adjusted quotes. A normal daily refresh therefore does not
currently preserve payout records even when the source can supply them.

### Accuracy and date checks

Issuer records are needed for precision and payment dates. Concrete checks:

- SHY, ex-date 2025-12-19: Yahoo reports USD 0.255; iShares reports USD 0.254847,
  payable 2025-12-24. [iShares distribution table](https://www.ishares.com/us/products/239452/ishares-13-year-treasury-bond-etf)
- DBC, ex-date 2025-12-22: Yahoo reports USD 0.744; Invesco's notice reports
  USD 0.74424, payable 2025-12-26. [Invesco distribution notice](https://www.invesco.com/content/dam/invesco/us/en/documents/tax-centre/Distribution-Qualified-Notices-25.12.09.pdf)
- TYD, ex-date 2020-12-10: Yahoo reports USD 5.735; the OCC notice reports
  USD 5.735260, payable 2020-12-17. This is also a reminder to retain special
  cash payouts when calibrating models.

The event API provides amounts and event timestamps, not a complete payment-date
or declaration-date history. Its amounts can be rounded. Split and reverse-split
handling must be checked: BWX, UPRO, TYD, TMF and UGL returned split events.
Store whether a per-share amount is as paid or expressed on an adjusted share
basis, and align prices and dividends before taking ratios.

Use issuer histories for the same funds as the accuracy/date reference: iShares
for SHY/IEF/TLT/ISHG, Vanguard for VT/BND, State Street for BWX/BWZ/GLD, ProShares
for UPRO/UGL, Direxion for TYD/TMF, and Invesco for DBC. Complete automated issuer
adapters have not been implemented or validated in this investigation.

## Why simple subtraction is insufficient

For a single, consistent security with a cash-reinvestment convention satisfying

```text
r_total[t] = (P[t] + D[t]) / P[t-1] - 1
r_price[t] = P[t] / P[t-1] - 1
```

the daily distribution contribution and amount are

```text
d[t] = r_total[t] - r_price[t]
D[t] = P[t-1] * d[t]
```

This is a conditional identity. It cannot be applied to unlike benchmarks,
gross/net return pairs or collateral-return pairs. Nor is `Adj Close - Close`
a cash payment. Annual compounded TR minus annual compounded PR is also not
an annual cash amount; reinvestment changes the path.

Even matched Yahoo prices/adjusted prices do not reproduce cash perfectly under
this simple identity. For DBC on 2025-12-22, it gives USD 0.753557733 per source
share versus the vendor event of USD 0.744 and issuer amount of USD 0.74424.
The source's backward dividend-adjustment convention explains why an
adjustment-factor calculation is closer:

```text
f[t] = adjusted_price[t] / price[t]
D_vendor_implied[t] = P[t-1] * (1 - f[t-1] / f[t])
```

For that observation the factor formula gives about USD 0.743999481. It is a
diagnostic under that convention, not a replacement for actual event records,
and still does not recover issuer precision, payment dates or share-basis details.

Two further audit findings matter:

- The pre-1988 USLCAP columns come from different portfolios, so their difference
  includes relative performance, not just dividends.
- Freshly retrieved `^GSPC`/`^SP500TR` data reproduce material negative inferred
  dividend contributions in parts of the matching-index era: for example,
  approximately -1.81537% on 1990-01-24 and -0.57281% on 2019-07-03. There are
  21 matching-era observations below -0.01% daily. These require investigation
  or explicitly modeled replacements before publishing a daily dividend series.
  The cause has not been established. Silently clipping negative values would
  distort cumulative income.

Small negative fund gaps, typically around a few parts per million in this
probe, can be numerical artifacts. Tolerances must distinguish those from
material anomalies. There is no single tolerance that fixes all asset classes.

## USD output contract

Publish companion outputs first, preserving the established return files and
their meanings. Two unit conventions should be explicit.

**Fund event records** contain the payout per actual source-fund share, or a
clearly labeled adjusted-share basis. Suggested fields:

```text
Fund, Currency, Ex Date, Record Date, Pay Date,
Total Cash Distribution USD Per Share, Share Basis,
Source, Source URL, Retrieved At, Quality Flag
```

Retain declaration dates and issuer cash components when supplied. Payment and
record dates may be null until verified; they must not be invented. Unknown
cash events must be distinguishable from a verified zero payout. Estimated
dates or amounts require their own flags and model versions.

**Asset-class distribution outputs** contain a distribution return and, if USD
amounts are required, amounts per explicitly defined synthetic USD unit:

```text
Date, Asset, Distribution Return, Cash Distribution USD Per Unit,
Unit Definition, Pay Date, Basis, Source, Quality Flag, Model Version
```

For a source fund, a useful distribution contribution is the ex-date cash per
share divided by the preceding split-consistent price. For blends, combine
component distribution contributions using the same beginning-period weights,
available legs and calendars as the returns pipeline. Do not average dollar
payouts per share across different funds.

For example, GLBOND uses `0.45*d_BND + 0.55*d_BWX`. GLSTBOND uses the U.S. GDP
weight for SHY and the existing average of available ISHG/BWZ legs. Payment
records should retain constituent entitlements across the ex-date/pay-date gap.

Existing `Close` values are often rebased indices, not ETF prices. To express
cash in USD for the full synthetic history, define a companion ex-distribution
unit initially worth USD 100. Let its price be `S` and its distribution
contribution be `d`. A decomposition preserving the existing total-return path is:

```text
cash_usd_per_unit[t] = S[t-1] * d[t]
return_ex_distribution_residual[t] = existing_total_return[t] - d[t]
S[t] = S[t-1] * (1 + return_ex_distribution_residual[t])
```

The residual is an accounting decomposition; vendor adjustment conventions can
make it differ from the actual source-fund quoted price return. Label it
accordingly. If the goal is exact historical fund replication, build a separate
observed price-plus-cash ledger from prices and issuer events, and reconcile
its reinvested returns against the existing vendor-adjusted series with
documented tolerances. Do not silently redefine the existing `Price Return`.

The consuming simulator can calculate its own USD entitlement from
`position_value_before_ex_date * Distribution Return`. Alternatively it can
multiply per-unit cash by its synthetic unit holdings. A USD 100 synthetic
unit is not a promise to equal one share of the source ETF.

Account for entitlement on the ex-date and availability on the payment date.
Cash receivables prevent an artificial drop in total wealth while payment is
pending. Reinvestment, withdrawals and tax handling remain consumer decisions.

## Historical and future modeling

Fund inception bounds observed cash history. Extending total returns to 1970
does not make a corresponding payout history identifiable. A proposed policy:

| Asset family | Modeling approach | Main limitation |
|---|---|---|
| Treasury proxies | Extract the existing modeled coupon-carry component; aggregate accrued income to a payout calendar calibrated to SHY/IEF/TLT. Use fund observations to calibrate yield-to-payout behavior. | Carry accrual is not a coupon payment or an ETF declaration. Yield to maturity alone is not the cash distribution yield. |
| Global bond proxies | Preserve or reconstruct local coupon/carry inputs and convert modeled cash to USD; calibrate payout behavior against the current component funds. | Annual overlays, monthly smoothing and FX path construction do not identify actual fund payments. Observed component cash is already USD. |
| Equity proxies | Fit dividend growth/yield and seasonal payment behavior to validated index information or VT history; include dividend cuts and regimes. | Earlier benchmarks differ; contemporary average yields are weak estimates for every historical regime. |
| UPRO/TYD/TMF | Use the same fund's observed payout behavior, separately representing routine and special payments; condition on interest-rate/collateral and return regimes where supportable. | Payouts are not a leverage multiple of underlying dividends; sample size is limited. |
| DBC-like commodities | Fit payout occurrence and size to DBC events and available collateral-income information; preserve the many zero-payout periods. | Only nine vendor cash events were found; futures/collateral TR does not uniquely determine shareholder cash. |
| GLD-like gold / UGL-like leveraged gold | Zero routine payout baseline under verified policy, with exceptional events supported. | A modeling baseline for synthetic periods and the future, not a mathematical prohibition. |

For forward simulations, sample or model returns and distributions jointly.
Preserve relevant rate dependence, seasonality and special payments. An
independent constant yield is a useful sensitivity scenario, but should be
identified as an assumption and stress-tested against alternatives. Exclude
future information when calibrating a historical out-of-sample exercise.

Distributions are already included in total return. For an illustrative single
period, USD 100,000 at 8% total return with a 3% distribution contribution gives
USD 105,000 remaining asset value plus USD 3,000 cash, before consumer-level
taxes or spending. Adding cash on top of USD 108,000 would count it twice.

## Recommended implementation sequence and validation

1. Add one shared corporate-action downloader/parser for the current fund
   symbols. Cache full fund event histories and prices once; deduplicate SHY
   across assets. Add a separate recent-event refresh to the daily workflow.
   Include announced future payment dates separately from completed history.
2. Add issuer verification for total cash and dates. Reconcile annual cash
   totals, check splits/reverse splits and ensure cash components are not
   double-counted when Yahoo groups them differently. Date revisions and
   year-end corrections need a longer reconciliation window than the current
   14-day price overlap, plus periodic full event checks.
3. Publish observed per-fund USD events and asset distribution contributions.
   Construct blend contributions with the exact production weight/calendar
   rules. Store observed, inferred, modeled, unknown and verified-zero states.
4. Add a separate historical modeled layer for the pre-fund periods and the
   unresolved USLCAP portions. Version its payout and yield assumptions.
   Preserve existing total-return outputs while validating any new decomposition.
5. Export calibration summaries such as trailing/annual payout yields,
   payout months, special-payment frequencies and model parameters for the
   separate simulator. Fund cash amounts alone are not forecasts.

Validation should cover USD currency and share basis, unique events and date
ordering, issuer totals, payment lags, source coverage, blend weights,
split continuity, material negative residuals, unit-price positivity and
reinvestment reconciliation. Verify that zero historical payouts for GLD/UGL
are explicit verified states, and that future event ingestion is not disabled.

No new commercial data subscription is demonstrated to be necessary for an
initial observed-fund layer. A complete issuer-verified long historical layer
and defensible pre-inception models require additional work. Public access to
vendor or issuer data does not establish permission to redistribute it; retain
the repository's existing source-rights review.

## Reproduction and retained evidence

Local research scripts and diagnostics are ignored exploratory files:

- `data/interim/audit_distribution_feasibility.py`
- `data/interim/distribution_feasibility_audit.json`
- `data/interim/probe_current_fund_distributions.py`
- `data/interim/current_fund_distribution_probe.json`
- `data/interim/summarize_distribution_research.py`
- `data/interim/cache_distribution_policy_sources.py`

Raw source responses and manifests are under the ignored directory
`sources/raw/distribution_research_2026_10_28/`. The event retrieval manifest
records URL, UTC access time, SHA-256 hash, observed quote coverage, event
counts and unresolved methodology/rights constraints for each source.

The policy-source manifest also records failed direct downloads: the SEC UGL
HTML returned HTTP 403 to the local downloader and the Invesco PDF returned
HTTP 406. Those response files are not accepted documents. Both documents were
successfully inspected through the web research tool at the primary URLs linked
above. The GLD prospectus, UGL issuer page and SHY issuer page were also saved
successfully as local source evidence.

The CSV audit and fresh source probe support the observations in this note.
They are not a production distribution build or a claim that every historical
cash event has been reconciled to issuer records.
