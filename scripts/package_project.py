"""Package git-tracked source and evidence, and verify every archived checksum."""

import argparse
import hashlib
import json
import subprocess
from pathlib import Path
from zipfile import ZIP_DEFLATED, ZipFile


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    root = Path(__file__).resolve().parents[1]
    paths = (
        subprocess.run(["git", "ls-files", "-z"], cwd=root, capture_output=True, check=True)
        .stdout.decode()
        .split("\0")
    )
    paths = sorted(path for path in paths if path and path != "PACKAGE_MANIFEST.json")
    if not paths:
        raise SystemExit("Stage the project files in git before packaging")
    entries = []
    for name in paths:
        content = (root / name).read_bytes()
        entries.append(
            {"path": name, "bytes": len(content), "sha256": hashlib.sha256(content).hexdigest()}
        )
    manifest = {
        "project": "CreditLake",
        "version": "1.1.0",
        "file_count": len(entries),
        "files": entries,
    }
    (root / "PACKAGE_MANIFEST.json").write_text(json.dumps(manifest, indent=2) + "\n")
    output = args.output.resolve()
    output.parent.mkdir(parents=True, exist_ok=True)
    with ZipFile(output, "w", ZIP_DEFLATED, compresslevel=9) as archive:
        for name in [*paths, "PACKAGE_MANIFEST.json"]:
            archive.write(root / name, "creditlake/" + name)
    with ZipFile(output) as archive:
        for entry in entries:
            content = archive.read("creditlake/" + entry["path"])
            if (
                len(content) != entry["bytes"]
                or hashlib.sha256(content).hexdigest() != entry["sha256"]
            ):
                raise RuntimeError("Archive verification failed: " + entry["path"])
    print(
        json.dumps(
            {
                "output": str(output),
                "source_files_verified": len(entries),
                "archive_bytes": output.stat().st_size,
            }
        )
    )


if __name__ == "__main__":
    main()
