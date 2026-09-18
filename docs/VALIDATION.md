# Validation evidence

Validation ran on Linux with Python 3.12, using the pinned project dependencies.
The captured real-data test cutoff was **September 17, 2026**. JSON/XML evidence
and browser screenshots are included with the project.

| Check | Observed result | Evidence |
|---|---|---|
| Fresh end-to-end captured SEC pipeline | 10,738 inserts, eight issuers, 89 annual periods, 112 changed filing values | `evidence/full-pipeline-report.json` |
| Fresh pipeline elapsed time | 7.125 seconds in this local environment | `evidence/full-pipeline-report.json` |
| dbt build | Six models, 23 passing tests | `sample_outputs/dbt/run_results.json` |
| Python test suite | 39 passed, zero failures | `evidence/pytest.xml` |
| Isolated recovery verification | Source trace, replay, failed publication, recovery, retained old release, and two cutoff semantics passed | `evidence/recovery-validation.json` |
| Unchanged-source replay | Eight checkpoints skipped, zero inserts, serving release retained | `evidence/replay-report.json` |
| Airflow 2.11 DAG execution | Both tasks successful, no DAG import errors | `evidence/airflow-validation.json` |
| Browser interaction QA | Standalone and API-backed views pass; temporal filters, source details, exports, quality drilldown, error recovery; zero JavaScript errors | `evidence/dashboard-validation.json` |
| Desktop and mobile rendering | Both targets verified at 1365px and 390px; no page overflow; preview screenshots visually inspected | `../demo/dashboard-desktop.jpg`, `../demo/dashboard-mobile.jpg` |
| Synthetic normalization and loading | 100,000 verified rows; exact sum 104,999,950,000 USD | `evidence/benchmark.json` |
| Synthetic measured processing | 3.001 seconds: 1.037 normalization, 1.375 Parquet, 0.589 warehouse loading | `evidence/benchmark.json` |
| Larger synthetic normalization/load | 500,000 independently verified rows; 13.765 seconds; exact sum 624,999,750,000 USD | `evidence/benchmark-500k.json` |
| Standard-library serving smoke check | Quality, lineage, and metrics passed against a local Uvicorn API | `evidence/api-smoke-local.json` |
| Lint and formatting | Ruff check and format check passed | Repeat with `ruff check .` and `ruff format --check .` |

The synthetic benchmark is deliberately SEC-shaped generated data. It measures
normalization and Parquet/warehouse loading, excluding network acquisition,
dbt transformations, serving, and cloud execution. Its checksum-style monetary
sum and row count are independently verified. It is not a real-company volume
claim or a benchmark against another platform. Elapsed times depend on hardware
and concurrent workload.

## Behavior covered by automated tests

The suite covers source-to-Parquet lineage verification, named missing
metric reporting, balance-warning tolerance checks, release metrics, and readiness
checks for absent or missing serving databases. The quality report preserves the
original measured 35 complete / 54 incomplete annual periods and five balance
warnings. The earlier `test-console.txt` records the original 34-test run;
`pytest.xml` records the current 39-test run.

- Unchanged sources do not load twice or change the serving run ID.
- A failed ingestion does not advance a published checkpoint; replay inserts the pending facts.
- A failed publication or dbt build retains the prior readable release.
- Readers can use the previous warehouse while a candidate is being built.
- Annual revisions change latest views while an earlier filing-date query retains the old value.
- A quarterly duration cannot replace a full-year revenue figure.
- Observation-time cutoffs exclude historical filings discovered later by the platform.
- SCD2 metadata changes retain old intervals with exactly one current row.
- Excessive invalid data blocks publication and writes quarantine records, including all-invalid responses.
- A second writer is refused by the file lock.
- Changing the acquisition year range invalidates the source checkpoint.
- Dynamic API selection matches dbt canonical selections for all eight real issuers.
- Monetary fractions beyond floating-point precision survive normalization and Parquet storage exactly.
- Source archive downloads match their stored SHA-256.
- Invalid dates, unknown issuers, injection-shaped tickers, invalid table names, and excessive API limits are handled.
- The live client throttles requests, honors numeric Retry-After, and does not retry permanent 403 errors.

## Data quality warnings retained

The bundled dataset has **54 annual rows with fewer than ten mapped metrics**,
and **five balance-equation warnings** at the configured tolerance. These are
visible in the release report rather than hidden or filled with invented values.
Metric scope and independently revised filing evidence can affect the balance
equation. The coverage gate requires each issuer to have a revenue/assets period;
it does not assert that every issuer publishes every mapped metric every year.

## Validation boundaries

The actual source-capture script downloaded and verified the eight public SEC
responses. Default ingestion, dbt, exports, API, replay/recovery, source integrity,
Airflow tasks, and the browser demo were run locally. The live client's retry
cases use deterministic test doubles rather than deliberately triggering the
SEC's rate limits.

GitHub Actions executed the Python 3.11/3.12/3.13 matrix and Docker Compose
serving check successfully in [run 35256206486](https://github.com/sreemaanshivkirth05/creditlake-financial-data-platform/actions/runs/35256206486).
The [workflow history](https://github.com/sreemaanshivkirth05/creditlake-financial-data-platform/actions/workflows/ci.yml)
records checks for subsequent changes. Docker is unavailable in the local
validation environment; the container result is from CI. The standard-library
smoke script can also target a local API independently of Docker.

The refreshed interface passed Chromium 145 interaction checks in the
[dashboard CI job](https://github.com/sreemaanshivkirth05/creditlake-financial-data-platform/actions/runs/35367088922/job/105672063263).
Both the self-contained preview and API-backed workspace were tested at desktop
and mobile viewport widths. Screenshots from that run were visually inspected.
Backend API behavior is also checked by the Python suite and serving smoke
script. AWS and Snowflake deployment remain extensions. Windows and macOS were
not used for validation.

One test-run warning came from an upstream Starlette/AnyIO type alias deprecation;
it did not affect the API assertions or the suite result.
