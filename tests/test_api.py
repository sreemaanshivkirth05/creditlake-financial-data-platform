import gzip
import hashlib
import json

from fastapi.testclient import TestClient

from creditlake.api import create_app
from creditlake.config import Settings


def test_health_requires_a_release(tmp_path):
    client = TestClient(create_app(Settings.load(data_dir=tmp_path)))
    assert client.get("/health").status_code == 503


def test_dashboard_and_decimal_contract(real_settings):
    client = TestClient(create_app(real_settings))
    assert client.get("/").status_code == 200
    assert client.get("/health").json()["status"] == "ok"
    companies = client.get("/api/companies").json()
    assert len(companies) == 8
    response = client.get("/api/companies/TXN/facts?period_end=2023-12-31")
    assert response.status_code == 200
    facts = response.json()["facts"]
    assert len(facts) >= 8
    assert all(isinstance(row["value"], str) for row in facts)
    assert all(row["filing_url"].startswith("https://www.sec.gov/Archives/") for row in facts)
    archive = client.get(f"/api/facts/{facts[0]['fact_id']}/source")
    assert archive.status_code == 200
    data = gzip.decompress(archive.content)
    assert hashlib.sha256(data).hexdigest() == facts[0]["source_sha"]
    assert json.loads(data)["cik"] == 97476


def test_historical_cutoff_and_early_observation(real_settings):
    client = TestClient(create_app(real_settings))
    early = client.get("/api/companies/TXN/facts?as_of=2020-01-01").json()["facts"]
    assert early and all(row["filed"] <= "2020-01-01" for row in early)
    observed = client.get("/api/companies/TXN/facts?observed_before=2000-01-01T00:00:00Z")
    assert observed.json()["facts"] == []
    assert (
        client.get("/api/companies/TXN/facts?observed_before=2020-01-01T00:00:00").status_code
        == 422
    )


def test_invalid_queries_and_csv_export(real_settings):
    client = TestClient(create_app(real_settings))
    assert client.get("/api/companies/UNKNOWN/history").status_code == 404
    assert client.get("/api/companies/TXN/facts?as_of=not-a-date").status_code == 422
    assert client.get("/api/companies/TXN/revisions?limit=10000").status_code == 422
    assert client.get("/api/companies/TXN%27%20OR%201=1/history").status_code == 404
    assert client.get("/api/exports/raw.facts.csv").status_code == 422
    response = client.get("/api/exports/mart_company_trends.csv")
    assert response.status_code == 200
    assert "annual_key" in response.text.splitlines()[0]
