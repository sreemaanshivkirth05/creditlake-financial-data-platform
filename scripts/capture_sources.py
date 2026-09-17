"""Capture unmodified public SEC JSON for a reproducible offline demo.

For normal ingestion use `creditlake run --mode live`. This script is for
maintainers refreshing the bundled source snapshot, and always runs serially.
"""

import argparse
import gzip
import hashlib
import json
import time
import urllib.request
from datetime import UTC, datetime
from pathlib import Path


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--user-agent", required=True)
    args = parser.parse_args()
    root = Path(__file__).resolve().parents[1]
    destination = root / "fixtures" / "sec"
    destination.mkdir(parents=True, exist_ok=True)
    sources = []
    for issuer in json.loads((root / "config" / "issuers.json").read_text()):
        url = f"https://data.sec.gov/api/xbrl/companyfacts/CIK{issuer['cik']:010d}.json"
        request = urllib.request.Request(url, headers={"User-Agent": args.user_agent})
        with urllib.request.urlopen(request, timeout=60) as response:
            data = response.read()
        payload = json.loads(data)
        assert payload["cik"] == issuer["cik"]
        filename = f"CIK{issuer['cik']:010d}.json.gz"
        (destination / filename).write_bytes(gzip.compress(data, mtime=0))
        sources.append(
            {
                **issuer,
                "entity_name": payload["entityName"],
                "url": url,
                "file": filename,
                "sha256": hashlib.sha256(data).hexdigest(),
                "uncompressed_bytes": len(data),
                "captured_at": datetime.now(UTC).isoformat(),
            }
        )
        print(
            f"Captured {issuer['ticker']}: {payload['entityName']} ({len(data):,} bytes)",
            flush=True,
        )
        time.sleep(0.6)
    (destination / "manifest.json").write_text(json.dumps(sources, indent=2) + "\n")


if __name__ == "__main__":
    main()
