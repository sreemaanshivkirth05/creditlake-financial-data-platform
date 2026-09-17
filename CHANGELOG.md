# Changelog

## 1.1.0 — Portfolio verification and data observability

- Added immutable fact lineage from SEC response to Parquet and warehouse storage.
- Added financial coverage reports with named missing fields and balance warnings.
- Added Prometheus-compatible release metrics and serving readiness checks.
- Added a reproducible source-trace, replay, publication-failure, and recovery demonstration.
- Added five behavioral tests; all 39 Python tests passed locally.
- Measured a separate 500,000-row synthetic normalization and loading workload.
- Expanded architecture, coverage investigation, scaling, operations, and profile documentation.
- Configured Python-version CI jobs and a Docker Compose serving check.
- Pinned official Node 24 GitHub Actions to exact commits after remote CI surfaced runtime deprecations.

## 1.0.0 — Auditable financial platform

- Captured and verified actual SEC responses for eight DFW issuers.
- Implemented versioned fact loading, source contracts, quarantine, and SCD2 issuer history.
- Built six dbt models and 23 passing data-quality checks.
- Implemented atomic warehouse publication, a read-only API, and a responsive dashboard.
- Validated both Airflow tasks, replay, recovery, and historical cutoff semantics locally.
