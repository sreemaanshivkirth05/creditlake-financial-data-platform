from __future__ import annotations

import gzip
import hashlib
import json
import os
import shutil
import subprocess
import tempfile
import time
import uuid
from datetime import UTC, date, datetime
from pathlib import Path

from filelock import FileLock

from creditlake.config import NORMALIZER_VERSION, Settings
from creditlake.normalize import ContractError, digest, normalize
from creditlake.sources import SECClient, fixture_source
from creditlake.warehouse import connect, ingest_snapshot, initialize, literal, rows, save_silver


def write_json(path: Path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, indent=2, default=str) + "\n")


def release_manifest(data_dir: Path) -> dict | None:
    pointer = data_dir / "latest.json"
    return json.loads(pointer.read_text()) if pointer.exists() else None


def model_hash(settings: Settings) -> str:
    content = []
    for path in sorted((settings.root / "dbt").rglob("*")):
        if (
            path.is_file()
            and path.suffix in {".sql", ".yml"}
            and not any(part in {"target", "logs", "dbt_packages"} for part in path.parts)
        ):
            content.append([str(path.relative_to(settings.root)), path.read_text()])
    return digest(content)


def build_models(settings: Settings, warehouse: Path, build_dir: Path, as_of: date):
    build_dir.mkdir(parents=True, exist_ok=True)
    env = {
        **os.environ,
        "CREDITLAKE_WAREHOUSE": str(warehouse),
        "DBT_SEND_ANONYMOUS_USAGE_STATS": "false",
    }
    command = [
        shutil.which("dbt") or str(Path(os.sys.executable).parent / "dbt"),
        "build",
        "--project-dir",
        str(settings.root / "dbt"),
        "--profiles-dir",
        str(settings.root / "dbt"),
        "--target-path",
        str(build_dir / "target"),
        "--log-path",
        str(build_dir / "logs"),
        "--vars",
        json.dumps({"as_of": as_of.isoformat()}),
        "--no-use-colors",
        "--no-partial-parse",
    ]
    result = subprocess.run(command, env=env, text=True, capture_output=True, timeout=300)
    (build_dir / "dbt-console.log").write_text(result.stdout + result.stderr)
    if result.returncode:
        raise RuntimeError(
            f"dbt build failed; see {build_dir / 'dbt-console.log'}\n"
            + result.stdout[-1800:]
            + result.stderr[-600:]
        )
    report = json.loads((build_dir / "target" / "run_results.json").read_text())
    tests = [item for item in report["results"] if item["unique_id"].startswith("test.")]
    if not tests or any(item["status"] != "pass" for item in tests):
        raise RuntimeError("dbt did not produce an entirely passing quality test report")
    return {"models": len(report["results"]) - len(tests), "tests_passed": len(tests)}


def validate_warehouse(connection, issuer_ciks: list[int]) -> list[dict]:
    warnings = []
    for cik in issuer_ciks:
        count = connection.execute(
            "SELECT count(*) FROM analytics.fct_annual_financials WHERE cik=? AND assets IS NOT NULL",
            [cik],
        ).fetchone()[0]
        if not count:
            raise ContractError(
                f"CIK {cik} has no complete revenue/assets annual period at this cutoff"
            )
    missing = rows(
        connection,
        """
      SELECT d.ticker, f.period_end, f.available_metrics
      FROM analytics.fct_annual_financials f JOIN analytics.dim_issuer d USING (cik)
      WHERE available_metrics < 10 ORDER BY d.ticker, f.period_end
    """,
    )
    if missing:
        warnings.append({"check": "metric_completeness", "severity": "warning", "rows": missing})
    balance = rows(
        connection,
        """
      SELECT d.ticker, f.period_end, assets, liabilities, equity,
             assets - liabilities - equity AS residual
      FROM analytics.fct_annual_financials f JOIN analytics.dim_issuer d USING (cik)
      WHERE abs(assets - liabilities - equity) > greatest(1000, abs(assets) * 0.005)
    """,
    )
    if balance:
        warnings.append(
            {
                "check": "balance_equation",
                "severity": "warning",
                "rows": balance,
                "note": "Concept scope or filing revisions may differ; inspect source evidence",
            }
        )
    return warnings


def export_marts(connection, release_dir: Path):
    output = release_dir / "exports"
    output.mkdir(parents=True, exist_ok=True)
    for table in [
        "dim_issuer",
        "fct_annual_financials",
        "mart_company_trends",
        "mart_filing_revisions",
    ]:
        connection.execute(
            f"COPY analytics.{table} TO {literal(output / (table + '.parquet'))} "
            "(FORMAT PARQUET, COMPRESSION ZSTD)"
        )
        connection.execute(
            f"COPY analytics.{table} TO {literal(output / (table + '.csv'))} (FORMAT CSV, HEADER)"
        )


def atomic_publish(pointer: Path, manifest: dict):
    """The only serving commit. Both files are on the same local filesystem."""
    temporary = pointer.with_name(f".latest-{manifest['run_id']}.tmp")
    with temporary.open("w") as stream:
        json.dump(manifest, stream, indent=2, default=str)
        stream.write("\n")
        stream.flush()
        os.fsync(stream.fileno())
    os.replace(temporary, pointer)
    # Persist the directory entry where the host supports it.
    if os.name == "posix":
        directory_fd = os.open(pointer.parent, os.O_RDONLY)
        try:
            os.fsync(directory_fd)
        finally:
            os.close(directory_fd)


def run_pipeline(
    settings: Settings,
    *,
    mode: str = "fixture",
    as_of: date | None = None,
    user_agent: str | None = None,
    force: bool = False,
    fail_at: str | None = None,
    source_fetcher=None,
    model_builder=build_models,
    max_reject_rate: float = 0.005,
) -> dict:
    """Ingest only changed snapshots and atomically publish a validated release.

    Injectable adapters enable failure tests without public network access.
    Checkpoints travel with the candidate warehouse, never with partial work.
    """
    if mode not in {"fixture", "live"}:
        raise ValueError("mode must be fixture or live")
    if not 0 <= max_reject_rate <= 1:
        raise ValueError("max_reject_rate must be in [0,1]")
    as_of = as_of or datetime.now(UTC).date()
    settings.data_dir.mkdir(parents=True, exist_ok=True)
    client = None
    if mode == "live" and source_fetcher is None:
        client = SECClient(user_agent or os.getenv("SEC_USER_AGENT", ""))
    with FileLock(str(settings.data_dir / ".pipeline.lock"), timeout=0):
        run_id = uuid.uuid4().hex
        observed = datetime.now(UTC)
        started = time.monotonic()
        run_dir = settings.data_dir / "runs" / run_id
        release_dir = settings.data_dir / "releases" / run_id
        run_dir.mkdir(parents=True)
        release_dir.mkdir(parents=True)
        # Working WAL files belong on a local scratch filesystem, not on a
        # potentially synced artifact directory. Publish only a closed database.
        work_dir = tempfile.TemporaryDirectory(prefix="creditlake-candidate-")
        candidate = Path(work_dir.name) / "warehouse.duckdb"
        published_warehouse = release_dir / "warehouse.duckdb"
        previous = release_manifest(settings.data_dir)
        if previous:
            shutil.copy2(settings.data_dir / previous["warehouse"], candidate)
        connection = connect(candidate)
        initialize(connection)
        stats = {
            "run_id": run_id,
            "status": "running",
            "mode": mode,
            "started_at": observed.isoformat(),
            "filing_date_cutoff": as_of.isoformat(),
            "snapshots_loaded": 0,
            "snapshots_skipped": 0,
            "facts_inserted": 0,
            "rejected_rows": 0,
            "issuers": [],
            "model_hash": model_hash(settings),
        }
        write_json(run_dir / "report.json", stats)
        published = False
        try:
            for issuer in settings.issuers:
                if source_fetcher:
                    data, url = source_fetcher(issuer["cik"])
                elif client:
                    data, url = client.fetch(issuer["cik"])
                else:
                    data, url = fixture_source(settings.root, issuer["cik"])
                source_sha = hashlib.sha256(data).hexdigest()
                snapshot_id = digest([issuer, source_sha, NORMALIZER_VERSION, settings.min_year])
                if connection.execute(
                    "SELECT 1 FROM ops.snapshots WHERE snapshot_id=?", [snapshot_id]
                ).fetchone():
                    stats["snapshots_skipped"] += 1
                    continue
                bronze_relative = f"bronze/cik={issuer['cik']}/{source_sha}.json.gz"
                bronze = settings.data_dir / bronze_relative
                bronze.parent.mkdir(parents=True, exist_ok=True)
                if not bronze.exists():
                    bronze.write_bytes(gzip.compress(data, mtime=0))
                try:
                    entity, facts, rejected, telemetry = normalize(
                        data, issuer["cik"], settings.min_year
                    )
                except ContractError as exc:
                    if exc.rejected:
                        write_json(
                            settings.data_dir / "quarantine" / run_id / f"{issuer['cik']}.json",
                            exc.rejected,
                        )
                        stats["rejected_rows"] += len(exc.rejected)
                    if exc.telemetry:
                        write_json(run_dir / f"schema-{issuer['cik']}.json", exc.telemetry)
                    raise
                write_json(run_dir / f"schema-{issuer['cik']}.json", telemetry)
                if rejected:
                    write_json(
                        settings.data_dir / "quarantine" / run_id / f"{issuer['cik']}.json",
                        rejected,
                    )
                stats["rejected_rows"] += len(rejected)
                reject_rate = len(rejected) / (len(facts) + len(rejected))
                if reject_rate > max_reject_rate:
                    raise ContractError(
                        f"CIK {issuer['cik']} rejected {reject_rate:.2%} of supported facts; "
                        f"limit is {max_reject_rate:.2%}"
                    )
                silver_relative = f"silver/cik={issuer['cik']}/snapshot={snapshot_id}/facts.parquet"
                silver = settings.data_dir / silver_relative
                # A prior uncommitted attempt may have written this partition.
                # Recreate it with the new observation time; published source versions
                # are skipped above and therefore never overwritten.
                save_silver(
                    connection, facts, silver, observed, source_sha, bronze_relative, snapshot_id
                )
                inserted = ingest_snapshot(
                    connection,
                    issuer=issuer,
                    entity=entity,
                    snapshot_id=snapshot_id,
                    source_sha=source_sha,
                    source_url=url,
                    bronze_path=bronze_relative,
                    silver_path=silver,
                    silver_relative=silver_relative,
                    accepted=len(facts),
                    rejected=len(rejected),
                    telemetry=telemetry,
                    observed=observed,
                )
                stats["snapshots_loaded"] += 1
                stats["facts_inserted"] += inserted
                stats["issuers"].append(
                    {
                        "ticker": issuer["ticker"],
                        "name": entity["name"],
                        "accepted": len(facts),
                        "inserted": inserted,
                        "rejected": len(rejected),
                    }
                )
            connection.execute("CHECKPOINT")
            connection.close()
            connection = None
            if fail_at == "after_ingest":
                raise RuntimeError("Injected failure after ingestion")
            if (
                previous
                and stats["snapshots_loaded"] == 0
                and not force
                and previous.get("model_hash") == stats["model_hash"]
                and previous["filing_date_cutoff"] == as_of.isoformat()
            ):
                stats.update(
                    status="unchanged",
                    published_run_id=previous["run_id"],
                    elapsed_seconds=round(time.monotonic() - started, 3),
                )
                write_json(run_dir / "report.json", stats)
                shutil.rmtree(release_dir)
                return stats
            stats["dbt"] = model_builder(settings, candidate, run_dir / "dbt", as_of)
            if (run_dir / "dbt").exists():
                shutil.copytree(run_dir / "dbt", release_dir / "dbt")
            connection = connect(candidate)
            stats["warnings"] = validate_warehouse(connection, [i["cik"] for i in settings.issuers])
            stats["total_facts"] = connection.execute("SELECT count(*) FROM raw.facts").fetchone()[
                0
            ]
            stats["annual_periods"] = connection.execute(
                "SELECT count(*) FROM analytics.fct_annual_financials"
            ).fetchone()[0]
            stats["revisions"] = connection.execute(
                "SELECT count(*) FROM analytics.mart_filing_revisions"
            ).fetchone()[0]
            export_marts(connection, release_dir)
            connection.execute("CHECKPOINT")
            connection.close()
            connection = None
            if fail_at == "before_publish":
                raise RuntimeError("Injected failure before publication")
            shutil.copyfile(candidate, published_warehouse)
            with published_warehouse.open("rb") as stream:
                os.fsync(stream.fileno())
            with connect(published_warehouse, read_only=True) as verification:
                actual = verification.execute("SELECT count(*) FROM raw.facts").fetchone()[0]
                if actual != stats["total_facts"]:
                    raise RuntimeError("Copied release failed independent verification")
            stats.update(
                status="success",
                published_at=datetime.now(UTC).isoformat(),
                elapsed_seconds=round(time.monotonic() - started, 3),
                warehouse=str(published_warehouse.relative_to(settings.data_dir)),
            )
            write_json(release_dir / "manifest.json", stats)
            write_json(run_dir / "report.json", stats)
            atomic_publish(settings.data_dir / "latest.json", stats)
            published = True
            return stats
        except Exception as exc:
            if connection is not None:
                connection.close()
                connection = None
            # If publication completed before a later fsync error, keep its release.
            current = release_manifest(settings.data_dir)
            published = published or bool(current and current.get("run_id") == run_id)
            stats.update(
                status="published_with_error" if published else "failed",
                error=str(exc),
                elapsed_seconds=round(time.monotonic() - started, 3),
            )
            write_json(run_dir / "report.json", stats)
            if not published and release_dir.exists():
                shutil.rmtree(release_dir)
            raise
        finally:
            if connection is not None:
                connection.close()
            work_dir.cleanup()
