"""Exercise a running container's API using only the Python standard library."""

import argparse
import json
from urllib.request import urlopen


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--url", default="http://127.0.0.1:8000")
    args = parser.parse_args()

    def fetch(path, *, text=False):
        with urlopen(args.url.rstrip("/") + path, timeout=15) as response:
            content = response.read().decode()
        return content if text else json.loads(content)

    health = fetch("/health")
    assert health["status"] == "ok"
    quality = fetch("/api/quality")
    assert quality["run_id"] == health["run_id"]
    assert quality["summary"]["issuers"] == 8
    fact = fetch("/api/companies/TXN/facts?period_end=2023-12-31")["facts"][0]
    trace = fetch(f"/api/facts/{fact['fact_id']}/lineage")
    assert trace["fact"]["value"] == fact["value"]
    assert trace["source"]["sha256"] == fact["source_sha"]
    assert "creditlake_serving_release_ready 1\n" in fetch("/metrics", text=True)
    print(
        json.dumps(
            {
                "status": "pass",
                "run_id": health["run_id"],
                "quality_summary": quality["summary"],
                "lineage_verified": True,
            }
        )
    )


if __name__ == "__main__":
    main()
