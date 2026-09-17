"""Run optional browser checks against the demo and a temporary local API.

Requires Node and `npm install --no-save playwright` plus a Playwright browser.
Keeping the API and browser as child processes also supports isolated runtimes.
"""

import os
import shutil
import subprocess
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path


def main():
    root = Path(__file__).resolve().parents[1]
    node = shutil.which("node")
    if not node:
        raise SystemExit("Install Node to run optional dashboard verification")
    log_path = root / "docs" / "evidence" / "dashboard-api.log"
    log_path.parent.mkdir(parents=True, exist_ok=True)
    with log_path.open("w") as log:
        server = subprocess.Popen(
            [sys.executable, "-m", "creditlake.cli", "serve", "--port", "8123"],
            cwd=root,
            stdout=log,
            stderr=log,
        )
        try:
            url = "http://127.0.0.1:8123"
            deadline = time.monotonic() + 15
            while True:
                try:
                    with urllib.request.urlopen(url + "/health", timeout=2) as response:
                        if response.status == 200:
                            break
                except urllib.error.URLError:
                    if server.poll() is not None or time.monotonic() > deadline:
                        raise RuntimeError(f"Temporary API did not start; see {log_path}") from None
                    time.sleep(0.2)
            subprocess.run(
                [node, str(root / "scripts" / "verify_dashboard.cjs")],
                cwd=root,
                env={**os.environ, "CREDITLAKE_API_URL": url},
                check=True,
                timeout=90,
            )
        finally:
            server.terminate()
            try:
                server.wait(timeout=5)
            except subprocess.TimeoutExpired:
                server.kill()
                server.wait(timeout=5)


if __name__ == "__main__":
    main()
