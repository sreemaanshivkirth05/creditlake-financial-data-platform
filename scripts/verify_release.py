"""Verify serving data independently of the pipeline task exit code."""

from creditlake.config import Settings
from creditlake.pipeline import release_manifest
from creditlake.warehouse import connect

settings = Settings.load()
manifest = release_manifest(settings.data_dir)
if not manifest or manifest["status"] != "success" or not manifest["dbt"]["tests_passed"]:
    raise SystemExit("No successful, quality-checked serving release")
with connect(settings.data_dir / manifest["warehouse"], read_only=True) as connection:
    count = connection.execute("SELECT count(*) FROM analytics.fct_annual_financials").fetchone()[0]
    if count != manifest["annual_periods"]:
        raise SystemExit("Release row count differs from manifest")
print(f"Verified published release {manifest['run_id']}: {count} annual periods")
