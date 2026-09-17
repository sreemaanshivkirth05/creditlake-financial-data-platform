"""Describe financial coverage without treating missing disclosures as healthy data."""

from __future__ import annotations

from decimal import Decimal

from creditlake.config import METRICS
from creditlake.warehouse import rows


def quality_report(connection) -> dict:
    metrics = list(METRICS)
    financials = rows(
        connection,
        """
        SELECT d.ticker, f.period_end, f.available_metrics,
               """
        + ", ".join("f." + metric for metric in metrics)
        + """
        FROM analytics.fct_annual_financials f
        JOIN analytics.dim_issuer d USING (cik)
        ORDER BY d.ticker, f.period_end
        """,
    )
    issuers = {}
    incomplete = []
    balances = []
    for record in financials:
        ticker = record["ticker"]
        issuer = issuers.setdefault(
            ticker,
            {
                "ticker": ticker,
                "annual_periods": 0,
                "complete_periods": 0,
                "missing_by_metric": dict.fromkeys(metrics, 0),
            },
        )
        issuer["annual_periods"] += 1
        missing = [metric for metric in metrics if record[metric] is None]
        if missing:
            incomplete.append(
                {"ticker": ticker, "period_end": record["period_end"], "missing_metrics": missing}
            )
            for metric in missing:
                issuer["missing_by_metric"][metric] += 1
        else:
            issuer["complete_periods"] += 1
        assets, liabilities, equity = (record[key] for key in ("assets", "liabilities", "equity"))
        if all(value is not None for value in (assets, liabilities, equity)):
            residual = assets - liabilities - equity
            # Match the release gate's SQL tolerance exactly, including decimal arithmetic.
            tolerance = max(Decimal(1000), abs(assets) * Decimal("0.005"))
            if abs(residual) > tolerance:
                balances.append(
                    {
                        "ticker": ticker,
                        "period_end": record["period_end"],
                        "assets": assets,
                        "liabilities": liabilities,
                        "equity": equity,
                        "residual": residual,
                        "tolerance": tolerance,
                    }
                )
    return {
        "summary": {
            "issuers": len(issuers),
            "annual_periods": len(financials),
            "complete_periods": len(financials) - len(incomplete),
            "incomplete_periods": len(incomplete),
            "balance_warnings": len(balances),
        },
        "metric_contract": metrics,
        "by_issuer": list(issuers.values()),
        "incomplete_periods": incomplete,
        "balance_warnings": balances,
        "interpretation": (
            "Missing metrics are unavailable under the configured whole-entity USD concept map, "
            "not zero values or healthy financial signals. A balance warning can result from "
            "concept scope or independently revised filing evidence; inspect the source before "
            "classifying it as a reporting error. This report describes the published annual mart."
        ),
    }


def fact_lineage(connection, fact_id: str) -> dict | None:
    records = rows(
        connection,
        """
        SELECT f.*, d.ticker, d.name, s.source_url, s.silver_path
        FROM raw.facts f JOIN ops.snapshots s USING (snapshot_id)
        JOIN analytics.dim_issuer d ON d.cik=f.cik
        WHERE f.fact_id=?
        """,
        [fact_id],
    )
    if not records:
        return None
    fact = records[0]
    accession = fact["accession"]
    duration = (fact["period_end"] - fact["period_start"]).days if fact["period_start"] else None
    annual_candidate = fact["form"] in {"10-K", "10-K/A"} and (
        fact["kind"] == "instant" or (duration is not None and 329 <= duration <= 399)
    )
    return {
        "fact": {
            key: value for key, value in fact.items() if key not in {"source_url", "silver_path"}
        },
        "source": {
            "company_facts_url": fact["source_url"],
            "filing_url": f"https://www.sec.gov/Archives/edgar/data/{fact['cik']}/"
            f"{accession.replace('-', '')}/{accession}-index.html",
            "sha256": fact["source_sha"],
            "archive_download": f"/api/facts/{fact_id}/source",
            "integrity_check": "Archive download verifies the original response SHA-256.",
        },
        "storage": {
            "bronze": fact["bronze_path"],
            "silver": fact["silver_path"],
            "raw_relation": "raw.facts",
            "snapshot_id": fact["snapshot_id"],
        },
        "annual_candidate": annual_candidate,
        "annual_model_path": (
            [
                "stg_annual_candidates",
                "stg_canonical_facts",
                "fct_annual_financials",
                "mart_company_trends",
            ]
            if annual_candidate
            else []
        ),
        "selection_note": (
            "This trace describes this immutable fact version. Eligibility is not proof that "
            "it is the selected annual value: canonical selection also applies the requested "
            "filing-date and observation-time cutoffs and version ranking."
        ),
    }
