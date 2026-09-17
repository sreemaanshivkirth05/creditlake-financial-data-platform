# Scaling and extension plan

The implemented platform uses eight real issuer snapshots and a single-node
warehouse. The following are proposed extensions, not performed deployments.
Each phase has an acceptance criterion so the scope follows evidence.

| Phase | Change | Acceptance evidence |
|---|---|---|
| Financial coverage | Reconcile supported concepts against filings; introduce separately named broader or derived metrics | Component-level lineage, reconciled examples, missing-data behavior, and cutoff tests |
| More issuers | Extend configuration and capture manifest using the throttled live client | Per-issuer coverage, replay without duplicates, source checksums, and bounded acquisition time |
| Quarterly reporting | Model standalone quarters separately from year-to-date and annual durations | Four-quarter reconciliation, 52/53-week handling, and amendment/late-filing tests |
| Cloud storage | Archive immutable bronze and silver objects in S3 with IAM roles and lifecycle rules | A real infrastructure deployment, readback checksum verification, and measured storage cost |
| Shared warehouse | Port dbt models to a supported shared warehouse such as Snowflake | Decimal precision, canonical selection parity, recovery, and simultaneous reader checks |
| Incremental marts | Recompute affected issuer-periods, including historical filing revisions and dependent YoY rows | Output parity with a full rebuild over revised and late-arriving data |
| Production operations | Record each source check, configure alerts, improve orchestration granularity, and document incidents | A demonstrated failure alert, retry, runbook recovery, and a source freshness dashboard |

## Cloud publication must preserve the contract

The local serving commit is a same-filesystem atomic pointer replacement. S3
does not implement a filesystem rename. A cloud profile must publish immutable
objects and coordinate checkpoints, validation, and the serving release through
a transactional catalog or suitable conditional-update protocol. Copying the
existing `os.replace` pattern to object storage would lose the correctness claim.

## When distributed processing would be justified

Measure acquisition, normalization, model build, memory, and concurrent queries
on representative workloads first. Spark would be appropriate only when that
workload exceeds a practical single-node execution budget. Kafka is appropriate
for an actual event-streaming source; full SEC Company Facts refreshes do not
become streaming transport simply by adding a message broker.

## Optional AI consumer

A research assistant could consume the read-only validated API, cite the exact
fact and filing evidence, and explain missing data. Financial calculations must
remain deterministic. Its evaluation should cover numerical fidelity, citations,
historical cutoff compliance, and refusal to infer values from missing metrics.
No LLM integration or trained credit-rating model is currently implemented.
