"""Measure synthetic normalization and Parquet/warehouse loading, not cloud scale."""

import argparse
import json
import tempfile
import time
from datetime import UTC, datetime
from pathlib import Path

from creditlake.normalize import normalize
from creditlake.warehouse import connect, ingest_snapshot, initialize, save_silver


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--rows", type=int, default=100_000)
    parser.add_argument("--output", type=Path, default=Path("docs/evidence/benchmark.json"))
    args = parser.parse_args()
    if not 1 <= args.rows <= 999_999:
        parser.error("rows must be between 1 and 999999")
    observations = [
        {
            "val": 1_000_000 + index,
            "end": f"{2015 + index % 10}-12-31",
            "filed": "2025-02-15",
            "accn": f"0000000001-25-{index + 1:06d}",
            "form": "10-K",
            "fy": 2024,
            "fp": "FY",
        }
        for index in range(args.rows)
    ]
    data = json.dumps(
        {
            "cik": 1,
            "entityName": "Synthetic Benchmark Issuer",
            "facts": {"us-gaap": {"Assets": {"units": {"USD": observations}}}},
        }
    ).encode()
    start = time.perf_counter()
    entity, facts, rejected, telemetry = normalize(data, 1, 2015)
    normalized_at = time.perf_counter()
    observed = datetime.now(UTC)
    with tempfile.TemporaryDirectory(prefix="creditlake-benchmark-") as temporary:
        directory = Path(temporary)
        connection = connect(directory / "benchmark.duckdb")
        initialize(connection)
        parquet = directory / "facts.parquet"
        save_silver(connection, facts, parquet, observed, "synthetic", "synthetic", "benchmark")
        parquet_at = time.perf_counter()
        issuer = {"cik": 1, "ticker": "BENCH", "sector": "Synthetic", "headquarters": "Synthetic"}
        inserted = ingest_snapshot(
            connection,
            issuer=issuer,
            entity=entity,
            snapshot_id="benchmark",
            source_sha="synthetic",
            source_url="synthetic",
            bronze_path="synthetic",
            silver_path=parquet,
            silver_relative="facts.parquet",
            accepted=len(facts),
            rejected=len(rejected),
            telemetry=telemetry,
            observed=observed,
        )
        loaded_at = time.perf_counter()
        # Independently verify content, not just a successful insert call.
        count, total = connection.execute("SELECT count(*),sum(value) FROM raw.facts").fetchone()
        expected = args.rows * 1_000_000 + args.rows * (args.rows - 1) // 2
        assert count == args.rows and total == expected and inserted == args.rows
        connection.close()
        report = {
            "dataset": "synthetic SEC-shaped USD asset observations",
            "input_rows": args.rows,
            "verified_rows": count,
            "verified_sum": str(total),
            "normalization_seconds": round(normalized_at - start, 3),
            "parquet_seconds": round(parquet_at - normalized_at, 3),
            "warehouse_load_seconds": round(loaded_at - parquet_at, 3),
            "total_measured_seconds": round(loaded_at - start, 3),
            "source_bytes": len(data),
            "parquet_bytes": parquet.stat().st_size,
            "run_at": observed.isoformat(),
        }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, indent=2) + "\n")
    print(json.dumps(report, indent=2))


if __name__ == "__main__":
    main()
