# Financial coverage and investigation findings

## Measured coverage

The captured September 17, 2026 dataset contains 89 annual issuer-period records.
Thirty-five have all ten mapped metrics; 54 have at least one missing metric.
There are five balance-equation warnings. These findings do not prevent every
record from being useful: each configured issuer has an annual revenue/assets
period, while unavailable metrics and ratios remain null.

| Issuer | Annual periods | All ten metrics | Principal coverage findings |
|---|---:|---:|---|
| CBRE | 11 | 10 | Operating cash flow missing in one period |
| CPRT | 11 | 3 | Cash missing in six periods; operating cash flow in two |
| DHI | 11 | 0 | Operating income and classified current assets/liabilities unavailable under the map |
| EAT | 12 | 0 | Standalone total liabilities unavailable under the map |
| LUV | 11 | 0 | Standalone total liabilities unavailable under the map |
| T | 11 | 1 | Total liabilities unavailable in ten periods; operating cash flow in one |
| TXN | 11 | 10 | Operating cash flow missing in one period |
| WING | 11 | 11 | All mapped metrics available |

Run `creditlake quality` or inspect `sample_outputs/quality_report.json` for
the exact missing fields and periods. The report reflects the published cutoff;
it is not an assertion that today's taxonomy map covers every historical disclosure.

## What the original responses establish

An inspection of the captured US-GAAP concept maps found:

- DHI has no `OperatingIncomeLoss`, `AssetsCurrent`, or `LiabilitiesCurrent` concept
  in its captured standard-taxonomy response. The pipeline therefore cannot supply
  those fields from this map. This is not evidence that the company never discloses
  related information in its filing or a custom taxonomy.
- LUV and EAT have annual-form `LiabilitiesAndStockholdersEquity` observations,
  but no supported standalone total-liabilities observations from 2015 onward.
  AT&T has one such annual-form `Liabilities` observation, for 2015.
  `LiabilitiesAndStockholdersEquity` must not be relabeled as total liabilities.
- Copart's mapped carrying-value cash concept stops at the 2019 annual period
  in this capture. Its response also contains the broader cash-and-restricted-cash
  concept in later periods. That broader scope is not silently substituted for cash.

These are findings from the captured Company Facts responses, not a complete
manual reconciliation of the source filings. A broader contract could introduce
separately named metrics or explicit derived measures with component lineage.
It would need reconciled examples and tests before publication.

## Balance-equation warnings

Warnings use `abs(assets - liabilities - equity) > max($1,000, 0.5% of assets)`.
The source values remain unchanged.

| Issuer | Period end | Residual USD |
|---|---|---:|
| CBRE | 2016-12-31 | -88,655,000 |
| CBRE | 2020-12-31 | 385,660,000 |
| CBRE | 2025-12-31 | 433,000,000 |
| WING | 2015-12-26 | 5,137,000 |
| WING | 2016-12-31 | 6,802,000 |

Metrics are independently selected from their latest eligible filing evidence.
Concept scope and revised comparative presentation can therefore affect the
equation. Each warning is an investigation item, not a claim of an issuer error.
Use the facts and lineage endpoints to compare accessions, concepts, values,
and original source responses for each component.

## Operational interpretation

Passing dbt tests establish the encoded contracts, not universal financial
completeness. Missing current assets/liabilities produce an unavailable current
ratio rather than a healthy liquidity conclusion. A negative equity value is
valid data. A changed filing value is not automatically a formal restatement.

The `/metrics` endpoint reports published completeness and balance-warning
counts. `creditlake_release_age_seconds` measures time since publication and
must not be used as an SEC source freshness measure. A live system would also
track successful source checks and expected issuer filing cadence.
