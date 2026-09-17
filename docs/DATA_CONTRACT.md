# Financial data contract

## Source and coverage

The source is the public SEC Company Facts XBRL endpoint. Eight captured responses
are bundled unchanged, with endpoint URLs, capture times, CIKs, byte counts, and
SHA-256 checksums in `fixtures/sec/manifest.json`. Sector and headquarters fields
are curated project configuration rather than SEC fact fields.

| Ticker | Issuer | CIK |
|---|---|---:|
| TXN | Texas Instruments | 97476 |
| T | AT&T | 732717 |
| LUV | Southwest Airlines | 92380 |
| CBRE | CBRE Group | 1138118 |
| CPRT | Copart | 900075 |
| DHI | D.R. Horton | 882184 |
| WING | Wingstop | 1636222 |
| EAT | Brinker International | 703351 |

The [SEC API documentation](https://www.sec.gov/search-filings/edgar-application-programming-interfaces)
describes whole-entity facts and their separate units. Custom taxonomies, segment
facts, non-USD amounts, and bank-specific analysis are outside this contract.

## Supported metrics

Ordered concept fallbacks are executable in `src/creditlake/config.py`.

| Metric | Primary concept | Kind |
|---|---|---|
| Revenue | RevenueFromContractWithCustomerExcludingAssessedTax | Duration |
| Net income | NetIncomeLoss | Duration |
| Operating income | OperatingIncomeLoss | Duration |
| Operating cash flow | NetCashProvidedByUsedInOperatingActivities | Duration |
| Assets | Assets | Instant |
| Liabilities | Liabilities | Instant |
| Equity | StockholdersEquityIncludingPortionAttributableToNoncontrollingInterest | Instant |
| Current assets | AssetsCurrent | Instant |
| Current liabilities | LiabilitiesCurrent | Instant |
| Cash | CashAndCashEquivalentsAtCarryingValue | Instant |

Equity falls back to `StockholdersEquity`. Revenue and net income have additional
documented fallbacks. Where taxonomy scope differs, the balance equation is a
warning rather than an assertion that missing amounts must be fabricated.

## Observation validation

- CIK must match the requested issuer and the source envelope must have a US-GAAP concept map.
- Dates must be valid ISO dates; filing cannot precede period end and start cannot follow end.
- Accession must match `##########-##-######`.
- Values must be numeric, finite, within the decimal contract, and have no more than four fractional USD digits.
- Revenue, assets, liabilities, current assets/liabilities, and cash cannot be negative. Income, equity, and operating cash flow can be negative.
- Monetary values stay in reported USD as `DECIMAL(38,4)`; they are never interpreted as thousands or millions.
- Source `fy` and `fp` are retained as filing hints, not used as the economic period's fiscal year.
- Supported observations ending before `min_year` are not acquired. Expanding the range invalidates the checkpoint; previously acquired raw facts are retained.

## Annual selection and revisions

Annual candidates come from 10-K and 10-K/A. Duration metrics must span 329–399
elapsed days, accommodating ordinary 52/53-week annual periods. Instants are
eligible, but the analytical annual table is anchored to annual revenue period
ends. Quarterly and year-to-date amounts remain in raw and cannot overwrite a
full-year revenue amount.

For an issuer, metric, and period end, select by:

1. Most recent filing date at or before the cutoff.
2. Lowest configured concept fallback priority within that filing date.
3. Descending accession, most recent platform first-observation time, then deterministic fact ID.

Every value version remains in raw. The revisions mart compares successive
values within the same issuer, concept, unit, start, and end. An unchanged
comparative value does not create an alert. A changed value is an observed
reporting change; it may reflect reclassification, presentation, or a restatement.

## Ratios and review flags

| Output | Definition |
|---|---|
| Net margin | Net income / revenue |
| Operating margin | Operating income / revenue |
| Current ratio | Current assets / current liabilities |
| Liabilities / assets | Total liabilities / total assets |
| Cash flow margin | Operating cash flow / revenue |
| Revenue YoY | Revenue / prior revenue − 1, only when period ends are 330–400 days apart |
| Liquidity review | Current ratio < 1 |
| Loss review | Net income < 0 |
| Cash flow review | Operating cash flow < 0 |

Missing numerators/denominators and zero denominators yield null ratios. A missing
current ratio is not a healthy liquidity conclusion. Review flags are descriptive
screening rules that require sector context; they are not predictions or ratings.
The ratios can combine the latest separately selected metric evidence from
different filings, so the API exposes each metric's source rather than claiming
one filing supplied every figure.

Financial JSON values are exact decimal strings. Chart coordinates and compact
UI labels use approximate JavaScript numbers for display; source values and
CSV/Parquet exports retain the stored precision.

## Schema evolution

Unknown concepts and extra observation fields generate telemetry. They do not
expand the metric contract automatically. Breaking shapes, an issuer with no
usable supported facts, excessive rejected observations, and failed dbt tests
block publication. A normalizer change requires incrementing `NORMALIZER_VERSION`
so existing source snapshots are reprocessed under the new contract.
