from __future__ import annotations

import argparse
import json
import sys
from datetime import date
from pathlib import Path

from creditlake.config import Settings
from creditlake.pipeline import release_manifest, run_pipeline
from creditlake.quality import quality_report
from creditlake.warehouse import connect


def main():
    parser = argparse.ArgumentParser(description="CreditLake auditable financial data platform")
    parser.add_argument("--root", type=Path)
    parser.add_argument("--data-dir", type=Path)
    parser.add_argument("--min-year", type=int, default=2015)
    commands = parser.add_subparsers(dest="command", required=True)
    run = commands.add_parser("run", help="Ingest, build, test, and atomically publish")
    run.add_argument("--mode", choices=["fixture", "live"], default="fixture")
    run.add_argument("--as-of", type=date.fromisoformat)
    run.add_argument("--force", action="store_true", help="Rebuild even when sources are unchanged")
    run.add_argument(
        "--fail-at", choices=["after_ingest", "before_publish"], help="Demonstrate recovery"
    )
    commands.add_parser("status", help="Print the latest validated release")
    commands.add_parser("quality", help="Explain missing financial metrics and balance warnings")
    serve = commands.add_parser("serve", help="Serve the dashboard and read-only API")
    serve.add_argument("--host", default="127.0.0.1")
    serve.add_argument("--port", type=int, default=8000)
    args = parser.parse_args()
    settings = Settings.load(args.root, args.data_dir, args.min_year)
    try:
        if args.command == "run":
            result = run_pipeline(
                settings, mode=args.mode, as_of=args.as_of, force=args.force, fail_at=args.fail_at
            )
            print(json.dumps(result, indent=2, default=str))
        elif args.command == "status":
            print(json.dumps(release_manifest(settings.data_dir), indent=2, default=str))
        elif args.command == "quality":
            manifest = release_manifest(settings.data_dir)
            if not manifest:
                raise RuntimeError("Run creditlake run before requesting a quality report")
            with connect(settings.data_dir / manifest["warehouse"], read_only=True) as connection:
                report = quality_report(connection)
            print(
                json.dumps(
                    {
                        "run_id": manifest["run_id"],
                        "as_of": manifest["filing_date_cutoff"],
                        **report,
                    },
                    indent=2,
                    default=str,
                )
            )
        elif args.command == "serve":
            import uvicorn

            from creditlake.api import create_app

            uvicorn.run(create_app(settings), host=args.host, port=args.port)
    except Exception as exc:
        print(f"CreditLake failed: {exc}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
