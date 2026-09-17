from __future__ import annotations

import gzip
import hashlib
import json
import re
import time
import urllib.error
import urllib.request
from pathlib import Path


class SECClient:
    """Serial, throttled source client. No credentials or paid API keys.

    A clear contact User-Agent is required for live access. 403 and other
    permanent errors fail immediately; only 429/5xx and transport errors retry.
    """

    def __init__(
        self,
        user_agent: str,
        *,
        timeout: int = 45,
        retries: int = 3,
        sleep=time.sleep,
        clock=time.monotonic,
        opener=urllib.request.urlopen,
    ):
        if not re.search(r"[^\s@]+@[^\s@]+\.[^\s@]+", user_agent):
            raise ValueError("Set SEC_USER_AGENT to a project name and a real contact email")
        self.user_agent = user_agent
        self.timeout = timeout
        self.retries = retries
        self.sleep, self.clock, self.opener = sleep, clock, opener
        self.last_request = float("-inf")

    def fetch(self, cik: int) -> tuple[bytes, str]:
        url = f"https://data.sec.gov/api/xbrl/companyfacts/CIK{cik:010d}.json"
        for attempt in range(self.retries + 1):
            self.sleep(max(0, 0.55 - (self.clock() - self.last_request)))
            self.last_request = self.clock()
            request = urllib.request.Request(
                url,
                headers={
                    "User-Agent": self.user_agent,
                    "Accept": "application/json",
                },
            )
            try:
                with self.opener(request, timeout=self.timeout) as response:
                    data = response.read(50_000_001)
                if len(data) > 50_000_000:
                    raise ValueError("SEC response exceeds the 50 MB source limit")
                return data, url
            except urllib.error.HTTPError as exc:
                if exc.code not in {429, 500, 502, 503, 504} or attempt == self.retries:
                    raise
                retry_after = exc.headers.get("Retry-After", "")
                delay = float(retry_after) if retry_after.isdigit() else 2**attempt
                self.sleep(min(60, max(1, delay)))
            except (urllib.error.URLError, TimeoutError):
                if attempt == self.retries:
                    raise
                self.sleep(2**attempt)
        raise RuntimeError("Retry loop exhausted")


def fixture_source(root: Path, cik: int) -> tuple[bytes, str]:
    directory = root / "fixtures" / "sec"
    manifest = json.loads((directory / "manifest.json").read_text())
    source = next((row for row in manifest if row["cik"] == cik), None)
    if source is None:
        raise ValueError(f"No bundled fixture for CIK {cik}")
    data = gzip.decompress((directory / source["file"]).read_bytes())
    if hashlib.sha256(data).hexdigest() != source["sha256"]:
        raise ValueError(f"Source checksum mismatch for CIK {cik}")
    return data, source["url"]
