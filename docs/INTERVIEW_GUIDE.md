# Portfolio and interview guide

## 60-second project explanation

“CreditLake is a financial data platform that converts SEC filings into an
auditable analytical warehouse. The difficult part is that a later filing can
change a prior year's number, and quarterly amounts can look like annual facts
if the period is ignored. The platform keeps all observed versions and selects
evidence using filing-date cutoffs. It uses Python ingestion, typed Parquet,
DuckDB, dbt, Airflow integration, and a read-only API. A new warehouse is built
and quality checked before publication, so a failed model build does not affect
the last working dashboard.”

## Five-minute demonstration

1. Open the dashboard and select Texas Instruments. Show annual revenue, margins, and fiscal period ends.
2. Apply a historical filing-date cutoff. Explain why future comparative values are excluded.
3. Open a filing evidence link and use the API's source archive endpoint to show the original JSON and its checksum.
4. Show `mart_filing_revisions`: a changed value is preserved along with its prior value and accession.
5. Run `creditlake run` a second time. The response reports zero inserts and skipped checkpoints.
6. Run `creditlake run --force --fail-at before_publish`, compare the serving run ID, then recover with `creditlake run --force`.
7. Show the dbt test report and the replay/restatement/observation-time tests.

The strongest evidence is the behavior you can demonstrate. Practice tracing
one actual figure through source JSON, a Parquet partition, `raw.facts`, the
canonical selection, and the financial mart.

## Questions you should be able to answer

**Why not store one row per company and year?**

Different filings report different values for the same economic period. A
single latest row erases evidence and causes look-ahead problems in historical
analysis. The raw grain therefore includes filing, period, concept, and value.

**What exactly is incremental?**

Snapshot checkpoints and raw fact loading. A changed issuer response is fetched
in full, but existing fact IDs do not insert again. Compact dbt marts are rebuilt
after changes. This deliberately avoids incomplete historical-period invalidation.

**How is this different from exactly-once message processing?**

It does not claim exactly-once source delivery. It provides idempotent loading
and an atomic serving commit. Retries can repeat acquisition and normalization,
but the serving release and its checkpoints move together only after validation.

**What happens if the fifth dbt model fails?**

The candidate stays unpublished. The API continues using the prior closed release,
and partial checkpoints cannot make future replay skip unfinished data.

**Why two time fields?**

The source filing date answers whether a filing existed by a date. Platform first
observation answers whether this system had discovered that value yet. Neither
is an exact reconstruction of historical intraday SEC acceptance time.

**Why are some financial fields missing?**

Companies use different taxonomy concepts and reporting scopes. The contract maps
a documented subset rather than inventing values. Missing inputs remain null;
coverage warnings identify where a reviewer should inspect the source.

**Where is SCD2 used?**

Issuer presentation attributes. A sector/name change closes the old half-open
validity interval and opens a new version. Financial marts use current metadata;
the full application-time history is kept separately.

**How would this move to AWS and Snowflake?**

Keep bronze/silver objects in S3, move checkpoints and release commits to a
transactional catalog, and port dbt relations to the Snowflake adapter. Use IAM
roles, managed orchestration, alerts, and explicit affected-period recomputation.
The project contains a local implementation and does not claim those services
have already been deployed.

## Resume wording

Use these after you have run the project and can demonstrate the behavior:

**CreditLake — Auditable Financial Data Platform**

- Implemented an SEC financial data pipeline with Python, Parquet, DuckDB, and dbt, preserving 10,738 fact versions across eight DFW issuers and producing 89 annual financial records with 23 passing data quality checks.
- Added filing-date and observation-time analytics, SCD2 issuer history, and atomic warehouse publication; validated idempotent replay and failure recovery, with a FastAPI dashboard and Airflow scheduling integration.

The counts describe the bundled dataset and local validation. Refreshing the
dataset may change them. Do not present the synthetic benchmark as real SEC
volume, the Airflow integration as a deployed cloud system, or review rules as
a trained credit risk model.

## Publish the portfolio

Create a repository named `creditlake-financial-data-platform`, add the source
files and real fixture manifest, and use the README as the repository landing
page. Include the dashboard screenshot and validation evidence. Keep generated
`data/` databases, local environments, and contact settings outside git.

The provided GitHub Actions workflow runs lint, tests, the captured SEC pipeline,
and an independent release check. Before interviews, rehearse one revision case
and one failure-recovery case from the tests without relying on memorized wording.
