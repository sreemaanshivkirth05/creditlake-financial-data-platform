import gzip
import hashlib
import json
from decimal import Decimal

from fastapi.testclient import TestClient

from creditlake.api import create_app
from creditlake.config import Settings
from creditlake.warehouse import connect


def test_metric_trace_matches_original_json_and_silver(real_settings):
    client = TestClient(create_app(real_settings))
    chosen = client.get("/api/companies/TXN/facts?period_end=2023-12-31").json()["facts"]
    fact = next(record for record in chosen if record["metric"] == "revenue")
    response = client.get(f"/api/facts/{fact['fact_id']}/lineage")
    assert response.status_code == 200
    trace = response.json()
    assert trace["fact"]["value"] == fact["value"]
    assert trace["fact"]["accession"] == fact["accession"]
    archive = client.get(trace["source"]["archive_download"])
    original = gzip.decompress(archive.content)
    assert hashlib.sha256(original).hexdigest() == trace["source"]["sha256"]
    observations = json.loads(original)["facts"]["us-gaap"][fact["concept"]]["units"]["USD"]
    assert any(
        row["accn"] == fact["accession"]
        and row["end"] == fact["period_end"]
        and Decimal(str(row["val"])) == Decimal(fact["value"])
        for row in observations
    )
    with connect(real_settings.data_dir / "trace-check.duckdb") as connection:
        observed = connection.execute(
            "SELECT value, accession, source_sha FROM read_parquet(?, hive_partitioning=false) "
            "WHERE fact_id=?",
            [str(real_settings.data_dir / trace["storage"]["silver"]), fact["fact_id"]],
        ).fetchone()
    assert str(observed[0]) == fact["value"]
    assert observed[1] == fact["accession"]
    assert observed[2] == trace["source"]["sha256"]
    assert trace["annual_candidate"] is True
    assert client.get("/api/facts/unknown/lineage").status_code == 404


def test_quality_explains_missing_fields_and_balance_scope(real_settings):
    client = TestClient(create_app(real_settings))
    quality = client.get("/api/quality").json()
    assert quality["summary"] == {
        "issuers": 8,
        "annual_periods": 89,
        "complete_periods": 35,
        "incomplete_periods": 54,
        "balance_warnings": 5,
    }
    assert sum(issuer["annual_periods"] for issuer in quality["by_issuer"]) == 89
    for missing in quality["incomplete_periods"]:
        history = client.get(f"/api/companies/{missing['ticker']}/history").json()["history"]
        record = next(row for row in history if row["period_end"] == missing["period_end"])
        assert all(record[metric] is None for metric in missing["missing_metrics"])
    for warning in quality["balance_warnings"]:
        assert abs(Decimal(warning["residual"])) > Decimal(warning["tolerance"])


def test_observability_distinguishes_publication_age_and_missing_data(real_settings):
    client = TestClient(create_app(real_settings))
    response = client.get("/metrics")
    assert response.status_code == 200
    assert "creditlake_serving_release_ready 1\n" in response.text
    assert "creditlake_incomplete_annual_periods 54\n" in response.text
    assert "creditlake_balance_warnings 5\n" in response.text
    assert "Seconds since publication; not source freshness." in response.text


def test_uninitialized_metrics_are_not_ready(tmp_path):
    client = TestClient(create_app(Settings.load(data_dir=tmp_path)))
    assert "creditlake_serving_release_ready 0\n" in client.get("/metrics").text
    assert client.get("/api/quality").status_code == 503


def test_missing_serving_database_is_not_ready(real_settings, tmp_path):
    manifest = TestClient(create_app(real_settings)).get("/api/status").json()
    (tmp_path / "latest.json").write_text(json.dumps(manifest))
    client = TestClient(create_app(Settings.load(data_dir=tmp_path)))
    assert manifest["status"] == "success"
    assert "creditlake_serving_release_ready 0\n" in client.get("/metrics").text
