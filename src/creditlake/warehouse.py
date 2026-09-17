from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path

import duckdb

from creditlake.normalize import digest

DDL = """
CREATE SCHEMA IF NOT EXISTS raw;
CREATE SCHEMA IF NOT EXISTS ops;
CREATE TABLE IF NOT EXISTS raw.facts (
    fact_id VARCHAR PRIMARY KEY, cik BIGINT NOT NULL, metric VARCHAR NOT NULL,
    concept VARCHAR NOT NULL, kind VARCHAR NOT NULL, alias_priority INTEGER NOT NULL,
    unit VARCHAR NOT NULL, period_start DATE, period_end DATE NOT NULL,
    value DECIMAL(38,4) NOT NULL, accession VARCHAR NOT NULL, form VARCHAR NOT NULL,
    filed DATE NOT NULL, fiscal_year_hint INTEGER, fiscal_period_hint VARCHAR,
    first_observed TIMESTAMPTZ NOT NULL, source_sha VARCHAR NOT NULL,
    bronze_path VARCHAR NOT NULL, snapshot_id VARCHAR NOT NULL
);
CREATE TABLE IF NOT EXISTS raw.issuer_history (
    issuer_key VARCHAR PRIMARY KEY, cik BIGINT NOT NULL, name VARCHAR NOT NULL,
    ticker VARCHAR NOT NULL, sector VARCHAR NOT NULL, headquarters VARCHAR NOT NULL,
    attribute_hash VARCHAR NOT NULL, valid_from TIMESTAMPTZ NOT NULL,
    valid_to TIMESTAMPTZ
);
CREATE TABLE IF NOT EXISTS ops.snapshots (
    snapshot_id VARCHAR PRIMARY KEY, cik BIGINT NOT NULL, source_sha VARCHAR NOT NULL,
    source_url VARCHAR NOT NULL, bronze_path VARCHAR NOT NULL, silver_path VARCHAR NOT NULL,
    ingested_at TIMESTAMPTZ NOT NULL, accepted_count BIGINT NOT NULL,
    rejected_count BIGINT NOT NULL, inserted_count BIGINT NOT NULL,
    schema_telemetry JSON NOT NULL
);
"""


def connect(path: Path, *, read_only=False):
    return duckdb.connect(str(path), read_only=read_only)


def initialize(connection):
    connection.execute(DDL)


def rows(connection, query: str, params=None) -> list[dict]:
    cursor = connection.execute(query, params or [])
    names = [column[0] for column in cursor.description]
    return [dict(zip(names, row, strict=True)) for row in cursor.fetchall()]


def literal(value: str | Path) -> str:
    return "'" + str(value).replace("'", "''") + "'"


def save_silver(
    connection,
    facts: list[dict],
    path: Path,
    observed: datetime,
    source_sha: str,
    bronze_path: str,
    snapshot_id: str,
):
    path.parent.mkdir(parents=True, exist_ok=True)
    ndjson = path.with_suffix(".jsonl")
    with ndjson.open("w") as stream:
        for fact in facts:
            stream.write(
                json.dumps(
                    {
                        **fact,
                        "first_observed": observed.isoformat(),
                        "source_sha": source_sha,
                        "bronze_path": bronze_path,
                        "snapshot_id": snapshot_id,
                    }
                )
                + "\n"
            )
    schema = """{
      fact_id:'VARCHAR', cik:'BIGINT', metric:'VARCHAR', concept:'VARCHAR',
      kind:'VARCHAR', alias_priority:'INTEGER', unit:'VARCHAR', period_start:'DATE',
      period_end:'DATE', value:'DECIMAL(38,4)', accession:'VARCHAR', form:'VARCHAR',
      filed:'DATE', fiscal_year_hint:'INTEGER', fiscal_period_hint:'VARCHAR',
      first_observed:'TIMESTAMPTZ', source_sha:'VARCHAR', bronze_path:'VARCHAR',
      snapshot_id:'VARCHAR'
    }"""
    connection.execute(f"""
      COPY (SELECT * FROM read_json({literal(ndjson)}, format='newline_delimited',
                                    hive_partitioning=false, columns={schema}))
      TO {literal(path)} (FORMAT PARQUET, COMPRESSION ZSTD, ROW_GROUP_SIZE 10000)
    """)
    ndjson.unlink()


def ingest_snapshot(
    connection,
    *,
    issuer: dict,
    entity: dict,
    snapshot_id: str,
    source_sha: str,
    source_url: str,
    bronze_path: str,
    silver_path: Path,
    silver_relative: str,
    accepted: int,
    rejected: int,
    telemetry: dict,
    observed: datetime,
) -> int:
    attributes = {
        "cik": issuer["cik"],
        "name": entity["name"],
        "ticker": issuer["ticker"],
        "sector": issuer["sector"],
        "headquarters": issuer["headquarters"],
    }
    attribute_hash = digest(attributes)
    current = connection.execute(
        "SELECT attribute_hash FROM raw.issuer_history WHERE cik=? AND valid_to IS NULL",
        [issuer["cik"]],
    ).fetchone()
    before = connection.execute("SELECT count(*) FROM raw.facts").fetchone()[0]
    connection.execute("BEGIN TRANSACTION")
    try:
        connection.execute(f"""
          INSERT INTO raw.facts BY NAME
          SELECT * FROM read_parquet({literal(silver_path)}, hive_partitioning=false)
          ON CONFLICT DO NOTHING
        """)
        after = connection.execute("SELECT count(*) FROM raw.facts").fetchone()[0]
        if current is None or current[0] != attribute_hash:
            connection.execute(
                "UPDATE raw.issuer_history SET valid_to=? WHERE cik=? AND valid_to IS NULL",
                [observed, issuer["cik"]],
            )
            connection.execute(
                "INSERT INTO raw.issuer_history VALUES (?,?,?,?,?,?,?,?,NULL)",
                [
                    digest([attribute_hash, observed.isoformat()]),
                    issuer["cik"],
                    entity["name"],
                    issuer["ticker"],
                    issuer["sector"],
                    issuer["headquarters"],
                    attribute_hash,
                    observed,
                ],
            )
        connection.execute(
            "INSERT INTO ops.snapshots VALUES (?,?,?,?,?,?,?,?,?,?,?)",
            [
                snapshot_id,
                issuer["cik"],
                source_sha,
                source_url,
                bronze_path,
                silver_relative,
                observed,
                accepted,
                rejected,
                after - before,
                json.dumps(telemetry),
            ],
        )
        connection.execute("COMMIT")
        return after - before
    except Exception:
        connection.execute("ROLLBACK")
        raise
