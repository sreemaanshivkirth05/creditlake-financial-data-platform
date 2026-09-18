# Operations and recovery

## First run

Use Python 3.11–3.13. From the project folder:

```bash
python -m venv .venv
source .venv/bin/activate
python -m pip install -e '.[dev]'
creditlake run
creditlake serve
```

Windows PowerShell activation: `.venv\Scripts\Activate.ps1`.
Open `http://127.0.0.1:8000` or the standalone `demo/CreditLake_Demo.html`.
The latter is a captured preview; it does not refresh itself from SEC.

Optional browser verification requires Node and Playwright:

```bash
npm install --no-save playwright@1.58.2
npx playwright install --with-deps chromium
python scripts/verify_ui.py
```

This starts a temporary API process and verifies the standalone and API dashboard,
including historical/empty cutoffs, company switching, charts, and mobile overflow.
The same check runs in CI. Reports and screenshots are written to
`validation/dashboard/` and uploaded as the `validation-dashboard` artifact.

Install through the project rather than installing only the Python wheel: the
repository includes the dbt project, configuration, and real source fixtures.
If running from elsewhere, set `CREDITLAKE_ROOT` to the unpacked project directory.

## Commands

| Action | Command |
|---|---|
| Ingest offline captured data | `creditlake run` |
| Fetch current SEC responses | `creditlake run --mode live` |
| Rebuild models despite unchanged sources | `creditlake run --force` |
| Publish a historical filing-date view | `creditlake run --as-of 2024-12-31` |
| Acquire an earlier year range | `creditlake --min-year 2010 run` |
| Inspect the serving release | `creditlake status` |
| Explain financial coverage | `creditlake quality` |
| Verify lineage, replay, and release recovery | `python scripts/verify_pipeline.py` |
| Serve dashboard and API | `creditlake serve --port 8000` |
| Create standalone demo | `python scripts/export_demo.py` |
| Measure synthetic load | `python scripts/benchmark.py --rows 100000` |
| Independently check publication | `python scripts/verify_release.py` |

An early publication cutoff must still yield an annual revenue/assets period for
each configured issuer. The read API can return an empty historical result for
a date before an issuer's first eligible filing.

## Live access

Set `SEC_USER_AGENT` to an identifying project name and your real contact email.
The SEC permits public API access without keys and has a fair-access limit of
10 requests/second. CreditLake uses serial requests with at least 0.55 seconds
between requests. See [SEC developer resources](https://www.sec.gov/about/developer-resources).

HTTP 429 and transient 5xx/transport errors retry with bounded backoff. HTTP 403
fails immediately. Check your User-Agent and the site's response before retrying;
the application does not attempt to bypass access controls.

## Where to inspect a run

- `data/latest.json`: the last validated serving release and measured counts.
- `data/releases/<id>/warehouse.duckdb`: the immutable serving warehouse.
- `data/releases/<id>/exports/`: CSV and Parquet analytical tables.
- `data/releases/<id>/dbt/target/`: dbt manifest and test run results.
- `data/runs/<id>/report.json`: success, unchanged, or failure report.
- `data/runs/<failed-id>/dbt/`: retained dbt failure logs.
- `data/quarantine/<id>/`: rejected source observations and reasons.
- `data/bronze/` and `data/silver/`: exact sources and normalized snapshot partitions.

Completeness and balance warnings are in the release report. Investigate them
using metric concept, accession, and the original source archive. They are not
filled with synthetic financial values.

## Failure recovery check

```bash
creditlake status
creditlake run --force --fail-at before_publish
creditlake status
creditlake run --force
```

The injected failure command intentionally exits with code 1. The serving run ID
and database remain unchanged. The final command publishes a new tested release.
`pytest` additionally proves that data learned by a failed ingest is reloaded
instead of skipped on replay.

Candidate warehouses from ordinary failures are removed; bronze and uncommitted
silver remain for replay. OS-backed file locks release when the owning process
exits. A killed process can leave an orphan candidate or run report marked
running, but the serving pointer still identifies the last completed publication.

Retain previous releases while serving readers. This implementation does not
automatically prune history. Back up the complete data directory together, since
warehouse source references are relative to its bronze/silver paths.

## Query examples

```bash
curl 'http://127.0.0.1:8000/api/companies/TXN/history?as_of=2023-12-31'
curl 'http://127.0.0.1:8000/api/companies/TXN/facts?period_end=2023-12-31&as_of=2025-01-01'
curl 'http://127.0.0.1:8000/api/companies/TXN/revisions?as_of=2025-01-01&limit=20'
```

Pass `observed_before=2026-09-17T12:00:00Z` to restrict facts to versions the
platform had already learned. Timezones are mandatory. Use the actual run times
from your own release. The source archive endpoint is
`/api/facts/<fact_id>/source`; it verifies the stored SHA-256 before serving JSON.gz.

Request `/api/facts/<fact_id>/lineage` to identify the original response,
Parquet partition, immutable raw fact, and annual model path. The trace describes
the requested version rather than asserting it is the current canonical value.
`/api/quality` reports named missing metrics, per-issuer coverage, and balance
warnings for the published annual mart.

## Monitoring metrics

`/metrics` exposes Prometheus-compatible gauges for serving readiness, fact and
annual-period counts, passing dbt checks, incomplete periods, balance warnings,
and release age. Readiness is zero when no release exists or its database cannot
be opened. Release age means time since publication, not time since the SEC was
successfully checked. A failed refresh can leave a valid older release serving;
inspect `data/runs/<id>/report.json` when diagnosing the latest attempt.

Suggested alert conditions include readiness zero, unexpected coverage changes,
and failed scheduled runs. The project provides metrics and structured reports;
an external monitoring backend and notifications are not configured.

## Docker and Airflow

```bash
docker compose up --build
docker compose --profile airflow up --build
```

The first command runs the fixture pipeline and serves the dashboard on port
8000. The Airflow profile adds the official Airflow 2.11 standalone development
environment on port 8080. Read its generated login from the container logs.
Find `creditlake_daily`, choose the `fixture` or `live` parameter, and trigger it.
The DAG starts paused; unpause it to enable the weekday 12:00 UTC schedule.

The data platform uses an isolated virtual environment inside the Airflow image
to keep dbt dependencies separate from Airflow's dependencies. Both containers
use UID 50000 for the shared data volume. The DAG has two tasks: build/test/publish,
then verify the closed release. This is a development environment, not an
authenticated production hosting configuration. See the
[official Airflow Docker guide](https://airflow.apache.org/docs/apache-airflow/2.11.0/howto/docker-compose/index.html).

Validation performed in this environment, including the limits of the optional
container path, is recorded in `VALIDATION.md`.
