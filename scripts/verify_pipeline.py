"""Verify source lineage, replay, release recovery, and temporal query behavior."""

from __future__ import annotations

import argparse
import json
import tempfile
from datetime import date
from pathlib import Path

from fastapi.testclient import TestClient

from creditlake.api import create_app
from creditlake.config import Settings
from creditlake.pipeline import release_manifest, run_pipeline
from creditlake.warehouse import connect


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    root = Path(__file__).resolve().parents[1]
    cutoff = date(2026, 9, 17)
    with tempfile.TemporaryDirectory(prefix="creditlake-verification-") as directory:
        settings = Settings.load(root, Path(directory))
        initial = run_pipeline(settings, as_of=cutoff)
        client = TestClient(create_app(settings))
        quality = client.get("/api/quality").json()
        facts = client.get("/api/companies/TXN/facts?period_end=2023-12-31").json()["facts"]
        evidence = next(fact for fact in facts if fact["metric"] == "revenue")
        trace = client.get(f"/api/facts/{evidence['fact_id']}/lineage").json()
        assert trace["fact"]["value"] == evidence["value"]
        replay = run_pipeline(settings, as_of=cutoff)
        assert replay["status"] == "unchanged" and replay["facts_inserted"] == 0
        assert release_manifest(settings.data_dir)["run_id"] == initial["run_id"]
        old_warehouse = settings.data_dir / initial["warehouse"]
        try:
            run_pipeline(settings, as_of=cutoff, force=True, fail_at="before_publish")
        except RuntimeError as exc:
            assert str(exc) == "Injected failure before publication"
        else:
            raise AssertionError("Expected the injected publication failure")
        assert client.get("/health").json()["run_id"] == initial["run_id"]
        assert release_manifest(settings.data_dir)["run_id"] == initial["run_id"]
        recovered = run_pipeline(settings, as_of=cutoff, force=True)
        assert recovered["run_id"] != initial["run_id"]
        assert recovered["total_facts"] == initial["total_facts"]
        with connect(old_warehouse, read_only=True) as connection:
            assert (
                connection.execute("SELECT count(*) FROM raw.facts").fetchone()[0]
                == initial["total_facts"]
            )
        historic = client.get("/api/companies/TXN/facts?as_of=2020-01-01").json()["facts"]
        assert historic and all(fact["filed"] <= "2020-01-01" for fact in historic)
        assert (
            client.get("/api/companies/TXN/facts?observed_before=2000-01-01T00:00:00Z").json()[
                "facts"
            ]
            == []
        )
        report = {
            "status": "pass",
            "fixture_cutoff": cutoff.isoformat(),
            "fact_versions": initial["total_facts"],
            "annual_periods": initial["annual_periods"],
            "dbt": initial["dbt"],
            "quality_summary": quality["summary"],
            "checks": {
                "source_trace": True,
                "idempotent_replay": True,
                "failed_publication_keeps_serving_release": True,
                "successful_recovery": True,
                "previous_release_still_readable": True,
                "historical_filing_cutoff": True,
                "observation_time_cutoff": True,
            },
            "example": {
                "ticker": "TXN",
                "metric": "revenue",
                "period_end": "2023-12-31",
                "value_usd": evidence["value"],
                "accession": evidence["accession"],
                "source_sha256": trace["source"]["sha256"],
            },
        }
    encoded = json.dumps(report, indent=2) + "\n"
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(encoded)
    print(encoded, end="")


if __name__ == "__main__":
    main()
