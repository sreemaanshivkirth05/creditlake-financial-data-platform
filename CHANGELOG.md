# Changelog

## 1.2.0 — Financial workspace refresh

- Replaced the dashboard with a light, responsive workspace and focused navigation.
- Connected fiscal-period selection to financial summaries, coverage, chart points, and evidence.
- Added exact-value source details and filing-cutoff-aware CSV exports.
- Added published-release coverage, missing-metric, and balance-review views.
- Split browser assets into maintainable HTML, CSS, and JavaScript; retained the self-contained export.
- Removed profile and interview material and standardized project verification commands.

## 1.1.0 — Recovery verification and data observability

- Added immutable fact lineage from SEC response to Parquet and warehouse storage.
- Added financial coverage reports with named missing fields and balance warnings.
- Added Prometheus-compatible release metrics and serving readiness checks.
- Added a reproducible source-trace, replay, publication-failure, and recovery demonstration.
- Added five behavioral tests; all 39 Python tests passed locally.
- Measured a separate 500,000-row synthetic normalization and loading workload.
- Expanded architecture, coverage investigation, scaling, and operations documentation.
- Configured Python-version CI jobs and a Docker Compose serving check.
- Pinned official Node 24 GitHub Actions to exact commits after remote CI surfaced runtime deprecations.

## 1.0.0 — Auditable financial platform

- Captured and verified actual SEC responses for eight DFW issuers.
- Implemented versioned fact loading, source contracts, quarantine, and SCD2 issuer history.
- Built six dbt models and 23 passing data-quality checks.
- Implemented atomic warehouse publication, a read-only API, and a responsive dashboard.
- Validated both Airflow tasks, replay, recovery, and historical cutoff semantics locally.
