# USD cash distributions

This companion layer supplies historical USD cash entitlements and payment
timing for a consumer maintained outside this repository. It includes 19
investable assets on their existing calendars, plus the exact 18 source funds
used by the daily return updater. CPI has no distribution. Existing return
schemas, observations and column meanings are preserved.

Cash distributions are distinct from tax allocations and earnings retained
inside a fund. Currency conversion, investor tax treatment, retirement rules
and future portfolio simulation belong to the consumer.

## Files and types

All outputs live in `data/processed/distributions/`. Each table has matching
CSV and Parquet versions. Both deliberately store **strings**: ISO dates,
fixed-point decimal amounts, and empty strings for unavailable values. This
preserves issuer precision and the distinction between an unknown and zero.
Read numeric columns explicitly as `Decimal` (or convert them deliberately to
your chosen numeric type). Parquet is compressed with Zstandard.

| File stem | Contract |
|---|---|
| `fund_events` | One row per fund/ex-date: actual as-paid USD per share, verified payment/record/declaration dates where supplied, issuer cash components, vendor comparison, share basis, sources and quality. |
| `fund_prices` | Native share prices, split ratios, quoted price return, vendor adjusted total return, distribution contribution and the adjustment residual. |
| Each existing investable asset stem | One daily row per original asset observation; synthetic unit value, unchanged original total return, cash entitlement, payments, receivable and quality. |
| `asset_cash_events` | One entitlement per asset/ex-date/constituent. Keeps verified and modeled payment dates in separate fields and fixes blend weights at entitlement. |
| `fund_coverage` | Quote coverage, event counts, issuer coverage, conflicts, missing payment dates and delivery status. |
| `annual_calibration` | Complete post-inception calendar years through the frozen calibration cutoff: sums of daily cash contributions, frequency and income features. |
| `calibration_summary` | Annual/event quantiles, payout frequency, zero years, largest payments, known gain/special components and evidence gaps. |
| `model_parameters.json` | Versioned parameters, calibration years, seasonality, ex-day assumptions, payment lags and extrapolation bounds. |

`sources/manifests/distributions_build.json` records artifact/input hashes,
source URLs, retrieval times, raw content hashes, coverage, weights, revision
audit and model assumptions. Raw downloads remain ignored. A hash of an HTTP
error document proves only a delivery failure; it is never accepted as a payout
record or as evidence of zero distributions.

## Fund shares and synthetic units

For an actual fund position, use `fund_events.Cash USD Per Share` multiplied by
the **actual shares entitled on its ex-date**. Yahoo historical prices and cash
are adjusted for later splits. The acquisition layer captures forward/reverse
splits through retrieval day, reconstructs native as-paid amounts and prices,
and takes the ratio on a consistent share basis. Issuer amounts that match the
vendor's adjusted units are converted with an explicit source note. Do not
multiply historical as-paid cash by today's split-adjusted share count.

For one source fund on ex-date t:

```text
d[t] = native cash per entitled share / preceding close in equivalent ex-date share units
```

The companion asset unit starts at **USD 100** on that asset's first row. It is
a synthetic unit of the asset proxy, never an actual ETF share. Cash remains
outside the unit. With original total return r[t]:

```text
cash entitlement[t] = unit value[t-1] * d[t]
residual return[t]  = r[t] - d[t]
unit value[t]      = unit value[t-1] * (1 + residual return[t])
receivable[t]      = receivable[t-1] + entitlement[t] - verified-date paid[t] - modeled-date paid[t]
```

The first row initializes the unit and earns no cash. A payment only transfers
the receivable into cash; it does not produce a second return. The residual
is the return needed to preserve the canonical total return **under this
synthetic cash convention**, not a claim of an independently observed ETF
price return. Reinvesting cash at each closing unit value reproduces the
original total-return path under the convention above. Keeping cash outside
the unit produces an unreinvested position instead.

`Pay Date` is filled only from verified issuer facts. Missing dates stay blank.
Asset entitlements with missing dates use separately labeled `Modeled Pay
Date`; default lags come from each fund's median verified lag, or a disclosed
seven-day assumption if none exists. Weekends move to the next weekday; public
holidays are not predicted. Index entitlements use an explicitly assumed
21-calendar-day lag. Daily tables bucket a payment on a non-observation day
into the next asset observation, while the event ledger retains the date.
Payments beyond the published calendar remain outstanding receivables.

The daily ledger describes one continuously held unit from the first row.
For a position opened later, use the event ledger and that position's ex-date
entitlements, as the consumer example does. Multiplying a later daily
receivable by newly purchased units would incorrectly include rights earned
before the purchase. Daily `Basis` describes that day's distribution
contribution; payment columns separately identify modeled timing.

## Evidence and reconciliation

Observed cash comes from Yahoo chart events plus the same funds' issuer
histories. Multiple vendor categories are resolved against the adjustment
factor to avoid double-counting dividend/capital-gain aliases. An ambiguous
overlap stops publication. Issuer components are kept separately and total
cash is counted once. Vendor field names do not establish tax character.

| Funds | Issuer evidence and limits |
|---|---|
| SHY, IEF, TLT, ISHG | iShares embedded full distribution tables, including income and gains. |
| VT, BND | Vanguard public product API, approximately ten years; earlier events retain vendor labels and unknown dates. |
| BWX, BWZ | State Street historical distribution workbook. |
| UPRO, SSO, UST, UBT | ProShares numeric-year API; historical years cached and recent two calendar years refreshed. |
| WLDU | No machine-readable issuer history; Yahoo cash events only (`vendor_only_no_issuer_history`). |
| TYD, TMF | Direxion fund-specific table parser; direct requests returned 403 during validation. Partial attributed issuer observations supplement vendor history, including TYD's 2020 special gain payment. |
| DBC | Direct Invesco delivery returned 406 or a dynamic page without validated history. Attributed 2025 issuer notice supplies precise cash/date for that event; remaining events retain vendor labels. |
| GLD, UGL | Vendor action histories plus prospectus/issuer policy evidence below; future exceptional cash is still ingested. |

Issuer cash precision takes priority and material conflicts remain visible in
both amount columns, quality flags and the audit. Issuer omission does not
delete a vendor-only event. Verified issuer-only historical events survive
rolling windows or temporary delivery failures; retaining them is audited.
A vendor withdrawal of previously published cash stops publication pending
investigation. Automatically interpreting a withdrawal as a cancellation
would silently erase an investor's cash history.

There are unresolved source disagreements. For example, some BND vendor
payments are double the issuer amounts; BWX's 2012-12 amount differs materially;
and State Street's BWX 2008-03-03 row lists a payment date before its ex-date.
That contradictory date is retained as `Source Pay Date`, quarantined from
usable `Pay Date`, and flagged. Vendor-only small/special payments remain
explicitly unreconciled. Issuer precedence is a reproducible choice, not proof
that every disputed observation is economically correct.

Yahoo uses backward dividend adjustments. Therefore quoted price return plus
cash/previous price need not exactly equal its adjusted total return. Both
are published along with `Adjustment Residual`; the residual is **not extra
cash**. The adjustment-factor relation
`previous_close * (1 - previous_factor/current_factor)` is a diagnostic for
vendor events, not a replacement for precise issuer cash. An unexplained
factor jump larger than 0.00001 of preceding price leaves fund cash unknown.

## Blends and historical models

GLBOND combines BND/BWX daily **distribution rates** with the production
45%/55% weights. GLSTBOND uses the production JST R6 GDP-weight function for
each year: SHY receives its actual U.S. weight, with the remainder shared among
international legs having a usable return that day. It follows the existing
calendar and missing-leg rules. Shares with different prices are never added
as though their dollar payouts were comparable. The ex-date weights remain
fixed for the eventual payment even across a year/weight boundary.

`Basis` distinguishes `observed`, `inferred`, `modeled`, `verified_zero` and
`mixed`. Fund `Cash Status` also distinguishes unknown adjustment dates from
an observed absence of vendor events. A missing quote/event combination falls
back to a flagged current-fund model in asset outputs; it never becomes an
observed zero. A modeled daily zero means no modeled payout was scheduled,
not an observation that a nonexistent historical fund paid nothing.

Models target hypothetical payout behavior of today's source funds before
those funds existed. They are retrospective backfills with future-calibrated
parameters, **not point-in-time forecasts**. Parameters are frozen between
explicit recalibrations. Calibration uses complete years after the first
quote year, ending December 31 before the initial requested end year.
Fund-inception transition years splice modeled calendars with observed
ex-dates; their resulting annual cash need not equal a complete modeled year.

- Treasury backfills retain the existing annual coupon/carry contribution
  and distribute it using the current fund's observed payout seasonality.
- VT uses its own median annual cash contribution relative to validated or
  modeled S&P income, with its own payout calendar.
- BND/BWX, international short bonds, leveraged funds and DBC fit their own
  annual contributions against STT income (ITT for BND/BWX). A negative fitted
  slope uses a disclosed constant median. Predicted negative cash is bounded
  at zero, and income states outside calibration range are flagged. Leveraged
  cash is never a fixed leverage multiple of underlying income.
- WLDU has no complete calendar year. Until it has three, it borrows SSO's fitted payout model and
  seasonality (`payout_model_proxy`). GLBOND2X and STT2X have no fund; their companions use UST's
  payout model as a disclosed modeled proxy on every date. New funds are added to frozen parameters
  without refitting existing models (`extended_funds`), and a new source fund triggers a full
  source reconciliation.
- Before DBC, collateral accrual is an income-state input to DBC's own fitted
  payout model; it is not treated as an actual shareholder payment.
- Seasonality uses observed contribution shares by month, typical ex-days,
  December's multiple-event behavior and verified payment lags. No future
  monthly payout is pulled into a partial last month.

These simple deterministic models omit policy changes, stochastic specials,
portfolio turnover and regime uncertainty. The empirical summaries preserve
large observed payouts and known gain/special counts for consumer modeling;
their annual contribution sums are **not buy-and-hold yields**. Component counts
are lower bounds where issuer components are unavailable. Annual averages
alone are unsuitable for modeling payment tails.

## USLCAP and zero-payout gold policies

Before 1988-01-05, USLCAP price and total return use unlike S&P/CRSP concepts.
Their difference is never labeled observed dividends. Matching later index
rows infer contributions only after anomaly checks. Material negative values
or daily contributions above 0.0015 contaminate the whole month and neighboring
spike months; those months use the disclosed model instead of retaining a
compensating positive spike. Small negatives within the larger of 0.000002
return or 0.02 index points/close are treated as measurement noise. Reallocating
them among positive days **preserves the signed monthly sum**. An entirely
negative month uses the model. No material negative is silently clipped.

The fallback uses the trailing median of 36 clean matching-index months once
12 are available; the initial reference is the first 36 clean months before
the cutoff. Early benchmark-mismatch months use that explicit hindsight
reference. Index income is an inferred contribution spread over observation
days, not a recovered fund payment schedule.

GLD uses a zero routine cash baseline. Its issuer-linked October 4, 2022
prospectus permits excess-cash distributions exceeding expected 12-month
expenses and USD 0.01 per share, and liquidation distributions after liabilities.
UGL's March 2026 Trust II prospectus states an expectation of no distributions;
its issuer page reports no distributions. These policies support routine zero,
not the impossibility of payouts. Pre-fund zeros are modeled; modern policy
zeros are distinct. Unexpected vendor/issuer events override the zero baseline.
URLs, verification dates and available document hashes are in
[`distribution_cash_policies.json`](../sources/derived/distribution_cash_policies.json)
and the [original prospectus investigation](research/distributions_feasibility.md).

## Refresh and publication

```powershell
python src/build_distributions.py --end-date 2026-10-26
python src/update_distributions.py --end-date 2026-10-26
python src/update_distributions.py --end-date 2026-10-26 --full-history
python src/build_distributions.py --end-date 2026-10-26 --offline
```

The normal all-dataset updater refreshes companions after successful return
updates when the distribution manifest exists. `--skip-distributions` is an
explicit local opt-out; it cannot pass the daily gate with stale companions.
The initial build fetches full histories; subsequent updates reconcile 400
calendar days with a seven-day price buffer and perform full source-history
checks at least every 31 days. Shared funds are acquired once. Historical
issuer years are cached; source rights and delivery failures remain recorded.
Use `--recalibrate` deliberately to revise modeled history and the version.
The builder and validation gate also check that their source-fund map still
matches the current daily updater; a later source change must update both.

All candidate arithmetic is checked before replacement. The manifest publishes
last; its hashes make an interrupted replacement fail the publication gate.
An unchanged refresh preserves output and manifest bytes. A newly due full
history check advances its recorded check date even if numerical data is
unchanged. No cross-file filesystem transaction is claimed.

The daily gate checks all companion hashes, CSV/Parquet equality, input hashes,
calendars, unit arithmetic, source objects, all current fund identities, cash
events/share basis and fresh quotes. A normal incremental update cannot rewrite
the companion prefix outside its reconciliation window without a full history
check or explicit model revision. Original return-history checks remain active.

Validation uses half-quantum rounding bounds: rates and unit cash use 12 decimal
places, prices eight. The native cash/rate bound adds half a rate quantum and
the exact effect of half a price quantum. Daily unit/payment arithmetic allows
only the documented output-rounding accumulation. Observed blend/source return
differences above 0.00001 are audited, not repaired by changing return inputs.

Run `python -m pytest -q tests/validation tests/automation`. Tests exercise
splits/reverse splits, source identity, payout aliases, amount conflicts,
payment dates, missing versus zero, blend weights, anomaly/model boundaries,
initial/incremental stability, issuer revisions, rejected candidates and the
complete published contract. On a Windows sandbox whose default temporary
directory is unavailable, add a fresh `--basetemp=data/interim/<test-run>`.

The [validation record](research/distributions_validation.md) reports the
clean/live/replay exercises, coverage counts and material reconciliation
residuals for the published initial release.

The runnable [consumer example](../examples/usd_distributions.py) loads either
format, uses Decimal and calculates USD cash for actual entitled fund shares
or an unreinvested synthetic asset position. A position bought at the selected
closing price earns entitlements strictly after that observation. Payment
amounts with modeled dates remain separate in its result.

Third-party data rights remain unresolved where stated. The code license does
not grant redistribution or commercial-use rights for issuer/vendor data or
the JST-derived weights. See [DATA_LICENSE.md](../DATA_LICENSE.md).
