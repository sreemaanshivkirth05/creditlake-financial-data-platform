from __future__ import annotations

import gzip
import hashlib
from datetime import UTC, date, datetime
from decimal import Decimal
from pathlib import Path
from typing import Literal

from duckdb import Error as DuckDBError
from fastapi import FastAPI, HTTPException, Query
from fastapi.encoders import jsonable_encoder
from fastapi.responses import FileResponse, JSONResponse, PlainTextResponse
from fastapi.staticfiles import StaticFiles

from creditlake.analytics import annual_history, canonical_facts, filing_revisions
from creditlake.config import Settings
from creditlake.pipeline import release_manifest
from creditlake.quality import fact_lineage, quality_report
from creditlake.warehouse import connect, rows


def encoded(value):
    # Monetary decimals remain exact strings at the wire boundary.
    return JSONResponse(jsonable_encoder(value, custom_encoder={Decimal: str}))


def create_app(settings: Settings | None = None) -> FastAPI:
    settings = settings or Settings.load()
    app = FastAPI(
        title="CreditLake",
        version="1.1.0",
        description=(
            "Read-only financial analytics. Filing-date cutoffs exclude later filings; "
            "optional observation cutoffs exclude facts first seen later by this platform. "
            "Currency values use exact decimal strings."
        ),
    )
    static = Path(__file__).parent / "static"
    app.mount("/static", StaticFiles(directory=static), name="static")

    def snapshot():
        manifest = release_manifest(settings.data_dir)
        if not manifest:
            raise HTTPException(503, "No published data. Run creditlake run first.")
        return manifest, settings.data_dir / manifest["warehouse"]

    def lookup(connection, ticker: str):
        issuers = rows(
            connection, "SELECT * FROM analytics.dim_issuer WHERE ticker=?", [ticker.upper()]
        )
        if not issuers:
            raise HTTPException(404, "Unknown issuer ticker")
        return issuers[0]

    @app.get("/", include_in_schema=False)
    def dashboard():
        return FileResponse(static / "index.html")

    @app.get("/health")
    def health():
        manifest, path = snapshot()
        with connect(path, read_only=True) as connection:
            connection.execute("SELECT 1 FROM analytics.dim_issuer LIMIT 1")
        return {"status": "ok", "run_id": manifest["run_id"]}

    @app.get("/api/status")
    def status():
        manifest, _ = snapshot()
        return encoded(manifest)

    @app.get("/api/quality")
    def quality():
        manifest, path = snapshot()
        with connect(path, read_only=True) as connection:
            report = quality_report(connection)
        return encoded(
            {"run_id": manifest["run_id"], "as_of": manifest["filing_date_cutoff"], **report}
        )

    @app.get("/metrics", response_class=PlainTextResponse)
    def metrics():
        manifest = release_manifest(settings.data_dir)
        gauges = {"creditlake_serving_release_ready": ("Validated release is readable.", 0)}
        if manifest:
            try:
                with connect(
                    settings.data_dir / manifest["warehouse"], read_only=True
                ) as connection:
                    summary = quality_report(connection)["summary"]
                gauges["creditlake_serving_release_ready"] = ("Validated release is readable.", 1)
                gauges.update(
                    {
                        "creditlake_financial_fact_versions": (
                            "Preserved fact versions.",
                            manifest["total_facts"],
                        ),
                        "creditlake_annual_periods": (
                            "Published company periods.",
                            summary["annual_periods"],
                        ),
                        "creditlake_incomplete_annual_periods": (
                            "Periods missing a mapped metric.",
                            summary["incomplete_periods"],
                        ),
                        "creditlake_balance_warnings": (
                            "Balance checks outside tolerance.",
                            summary["balance_warnings"],
                        ),
                        "creditlake_dbt_tests_passed": (
                            "Passing checks in this release.",
                            manifest["dbt"]["tests_passed"],
                        ),
                        "creditlake_release_age_seconds": (
                            "Seconds since publication; not source freshness.",
                            max(
                                0,
                                (
                                    datetime.now(UTC)
                                    - datetime.fromisoformat(manifest["published_at"])
                                ).total_seconds(),
                            ),
                        ),
                    }
                )
            except (OSError, DuckDBError):
                pass
        lines = []
        for name, (description, value) in gauges.items():
            lines.extend(
                [f"# HELP {name} {description}", f"# TYPE {name} gauge", f"{name} {value}"]
            )
        return PlainTextResponse("\n".join(lines) + "\n", media_type="text/plain; version=0.0.4")

    @app.get("/api/companies")
    def companies():
        _, path = snapshot()
        with connect(path, read_only=True) as connection:
            return encoded(rows(connection, "SELECT * FROM analytics.dim_issuer ORDER BY ticker"))

    @app.get("/api/companies/{ticker}/history")
    def history(ticker: str, as_of: date | None = None, observed_before: datetime | None = None):
        manifest, path = snapshot()
        if observed_before and observed_before.tzinfo is None:
            raise HTTPException(422, "observed_before requires a timezone")
        cutoff = as_of or date.fromisoformat(manifest["filing_date_cutoff"])
        with connect(path, read_only=True) as connection:
            issuer = lookup(connection, ticker)
            return encoded(
                {
                    "issuer": issuer,
                    "as_of": cutoff,
                    "history": annual_history(connection, issuer["cik"], cutoff, observed_before),
                    "run_id": manifest["run_id"],
                }
            )

    @app.get("/api/companies/{ticker}/facts")
    def facts(
        ticker: str,
        as_of: date | None = None,
        period_end: date | None = None,
        observed_before: datetime | None = None,
    ):
        manifest, path = snapshot()
        if observed_before and observed_before.tzinfo is None:
            raise HTTPException(422, "observed_before requires a timezone")
        cutoff = as_of or date.fromisoformat(manifest["filing_date_cutoff"])
        with connect(path, read_only=True) as connection:
            issuer = lookup(connection, ticker)
            return encoded(
                {
                    "as_of": cutoff,
                    "observed_before": observed_before,
                    "facts": canonical_facts(
                        connection, issuer["cik"], cutoff, period_end, observed_before
                    ),
                    "run_id": manifest["run_id"],
                }
            )

    @app.get("/api/companies/{ticker}/revisions")
    def revisions(
        ticker: str,
        limit: int = Query(20, ge=1, le=200),
        as_of: date | None = None,
        observed_before: datetime | None = None,
    ):
        manifest, path = snapshot()
        if observed_before and observed_before.tzinfo is None:
            raise HTTPException(422, "observed_before requires a timezone")
        cutoff = as_of or date.fromisoformat(manifest["filing_date_cutoff"])
        with connect(path, read_only=True) as connection:
            issuer = lookup(connection, ticker)
            return encoded(
                {
                    "revisions": filing_revisions(
                        connection, issuer["cik"], cutoff, limit, observed_before
                    ),
                    "run_id": manifest["run_id"],
                }
            )

    @app.get("/api/facts/{fact_id}/source")
    def source_archive(fact_id: str):
        _, path = snapshot()
        with connect(path, read_only=True) as connection:
            fact = connection.execute(
                "SELECT cik,bronze_path,source_sha FROM raw.facts WHERE fact_id=?", [fact_id]
            ).fetchone()
        if not fact:
            raise HTTPException(404, "Unknown fact")
        source = settings.data_dir / fact[1]
        try:
            verified = hashlib.sha256(gzip.decompress(source.read_bytes())).hexdigest() == fact[2]
        except (OSError, EOFError):
            verified = False
        if not verified:
            raise HTTPException(503, "Source archive failed integrity verification")
        return FileResponse(
            source, filename=f"CIK{fact[0]:010d}.json.gz", media_type="application/gzip"
        )

    @app.get("/api/facts/{fact_id}/lineage")
    def lineage(fact_id: str):
        manifest, path = snapshot()
        with connect(path, read_only=True) as connection:
            trace = fact_lineage(connection, fact_id)
        if trace is None:
            raise HTTPException(404, "Unknown fact")
        return encoded({"run_id": manifest["run_id"], **trace})

    @app.get("/api/exports/{table}.csv")
    def export(
        table: Literal[
            "dim_issuer", "fct_annual_financials", "mart_company_trends", "mart_filing_revisions"
        ],
    ):
        _, path = snapshot()
        return FileResponse(
            path.parent / "exports" / (table + ".csv"),
            filename=table + ".csv",
            media_type="text/csv",
        )

    return app


app = create_app()
