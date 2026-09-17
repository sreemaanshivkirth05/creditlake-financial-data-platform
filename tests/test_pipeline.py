import json
from datetime import date
from decimal import Decimal

import pytest
from conftest import AS_OF, fetcher, observation, published_connection
from filelock import FileLock, Timeout

from creditlake.analytics import canonical_facts
from creditlake.config import Settings
from creditlake.normalize import ContractError
from creditlake.pipeline import build_models, release_manifest, run_pipeline


def test_replay_is_idempotent(synthetic_settings, source):
    before = release_manifest(synthetic_settings.data_dir)
    report = run_pipeline(synthetic_settings, as_of=AS_OF, source_fetcher=fetcher(source))
    assert report["status"] == "unchanged"
    assert report["snapshots_skipped"] == 1
    assert report["facts_inserted"] == 0
    assert release_manifest(synthetic_settings.data_dir) == before


def test_failure_after_ingestion_keeps_checkpoint_and_replays(synthetic_settings, source):
    before = release_manifest(synthetic_settings.data_dir)
    source["facts"]["us-gaap"]["Assets"]["units"]["USD"].append(
        observation(2100, filed="2025-02-15", accession="0000000001-25-000001")
    )
    with pytest.raises(RuntimeError, match="Injected failure"):
        run_pipeline(
            synthetic_settings, as_of=AS_OF, source_fetcher=fetcher(source), fail_at="after_ingest"
        )
    assert release_manifest(synthetic_settings.data_dir) == before
    with published_connection(synthetic_settings) as connection:
        assert connection.execute("SELECT count(*) FROM ops.snapshots").fetchone()[0] == 1
        assert connection.execute("SELECT count(*) FROM raw.facts").fetchone()[0] == 10

    def verify_readers_then_build(settings, candidate, build_dir, cutoff):
        assert release_manifest(settings.data_dir) == before
        with published_connection(settings) as reader:
            assert reader.execute("SELECT count(*) FROM raw.facts").fetchone()[0] == 10
        return build_models(settings, candidate, build_dir, cutoff)

    report = run_pipeline(
        synthetic_settings,
        as_of=AS_OF,
        source_fetcher=fetcher(source),
        model_builder=verify_readers_then_build,
    )
    assert report["status"] == "success"
    assert report["facts_inserted"] == 1


def test_failure_before_publication_does_not_replace_data(synthetic_settings, source):
    before = release_manifest(synthetic_settings.data_dir)
    with pytest.raises(RuntimeError, match="Injected failure"):
        run_pipeline(
            synthetic_settings,
            as_of=AS_OF,
            source_fetcher=fetcher(source),
            force=True,
            fail_at="before_publish",
        )
    assert release_manifest(synthetic_settings.data_dir) == before
    with published_connection(synthetic_settings) as connection:
        assert (
            connection.execute("SELECT revenue FROM analytics.fct_annual_financials").fetchone()[0]
            == 1000
        )


def test_revision_and_quarter_do_not_overwrite_history(synthetic_settings, source):
    observations = source["facts"]["us-gaap"][
        "RevenueFromContractWithCustomerExcludingAssessedTax"
    ]["units"]["USD"]
    observations.append(
        observation(900, start="2023-01-01", filed="2025-02-15", accession="0000000001-25-000001")
    )
    observations.append(
        observation(350, start="2023-10-01", filed="2025-02-16", accession="0000000001-25-000002")
    )
    run_pipeline(synthetic_settings, as_of=AS_OF, source_fetcher=fetcher(source))
    with published_connection(synthetic_settings) as connection:
        old = canonical_facts(connection, 1, date(2024, 12, 31))
        new = canonical_facts(connection, 1, AS_OF)
        assert next(f for f in old if f["metric"] == "revenue")["value"] == 1000
        assert next(f for f in new if f["metric"] == "revenue")["value"] == 900
        assert (
            connection.execute("SELECT count(*) FROM raw.facts WHERE metric='revenue'").fetchone()[
                0
            ]
            == 3
        )
        assert (
            connection.execute("SELECT revenue FROM analytics.fct_annual_financials").fetchone()[0]
            == 900
        )
        revision = connection.execute(
            "SELECT previous_value,value FROM analytics.mart_filing_revisions"
        ).fetchone()
        assert revision == (Decimal(1000), Decimal(900))


def test_platform_observation_time_excludes_late_discovery(synthetic_settings, source):
    with published_connection(synthetic_settings) as connection:
        original_time = connection.execute("SELECT max(first_observed) FROM raw.facts").fetchone()[
            0
        ]
    # This historical filing is discovered after the platform's first run.
    source["facts"]["us-gaap"]["Assets"]["units"]["USD"].append(
        observation(2300, filed="2024-04-01", accession="0000000001-24-000003")
    )
    run_pipeline(synthetic_settings, as_of=AS_OF, source_fetcher=fetcher(source))
    with published_connection(synthetic_settings) as connection:
        old = canonical_facts(connection, 1, AS_OF, observed_before=original_time)
        new = canonical_facts(connection, 1, AS_OF)
        assert next(f for f in old if f["metric"] == "assets")["value"] == 2000
        assert next(f for f in new if f["metric"] == "assets")["value"] == 2300


def test_scd_type_two_preserves_metadata(synthetic_settings, source):
    path = synthetic_settings.root / "config" / "issuers.json"
    issuers = json.loads(path.read_text())
    issuers[0]["sector"] = "Updated sector"
    path.write_text(json.dumps(issuers))
    report = run_pipeline(synthetic_settings, as_of=AS_OF, source_fetcher=fetcher(source))
    assert report["facts_inserted"] == 0
    with published_connection(synthetic_settings) as connection:
        records = connection.execute(
            "SELECT sector,valid_from,valid_to FROM raw.issuer_history ORDER BY valid_from"
        ).fetchall()
        assert len(records) == 2
        assert records[0][0] == "Testing" and records[1][0] == "Updated sector"
        assert records[0][2] == records[1][1]
        assert records[1][2] is None


def test_excessive_rejections_block_release_and_create_quarantine(synthetic_settings, source):
    before = release_manifest(synthetic_settings.data_dir)
    source["facts"]["us-gaap"]["Assets"]["units"]["USD"][0]["val"] = -10
    with pytest.raises(ContractError, match="rejected"):
        run_pipeline(synthetic_settings, as_of=AS_OF, source_fetcher=fetcher(source))
    assert release_manifest(synthetic_settings.data_dir) == before
    quarantine = list((synthetic_settings.data_dir / "quarantine").rglob("*.json"))
    assert len(quarantine) == 1
    assert json.loads(quarantine[0].read_text())[0]["concept"] == "Assets"


def test_writer_lock_prevents_simultaneous_runs(synthetic_settings, source):
    with FileLock(str(synthetic_settings.data_dir / ".pipeline.lock")):
        with pytest.raises(Timeout):
            run_pipeline(synthetic_settings, as_of=AS_OF, source_fetcher=fetcher(source))


def test_dbt_failure_retains_last_release(synthetic_settings, source):
    before = release_manifest(synthetic_settings.data_dir)

    def failing_builder(*args):
        raise RuntimeError("simulated dbt test failure")

    with pytest.raises(RuntimeError, match="dbt test failure"):
        run_pipeline(
            synthetic_settings,
            as_of=AS_OF,
            source_fetcher=fetcher(source),
            force=True,
            model_builder=failing_builder,
        )
    assert release_manifest(synthetic_settings.data_dir) == before


def test_year_range_change_reprocesses_source(synthetic_settings, source):
    source["facts"]["us-gaap"]["Assets"]["units"]["USD"].append(
        observation(1500, end="2014-12-31", filed="2015-02-01", accession="0000000001-15-000001")
    )
    run_pipeline(synthetic_settings, as_of=AS_OF, source_fetcher=fetcher(source))
    wider = Settings.load(synthetic_settings.root, synthetic_settings.data_dir, 2014)
    report = run_pipeline(wider, as_of=AS_OF, source_fetcher=fetcher(source))
    assert report["facts_inserted"] == 1


def test_real_dataset_and_api_dbt_parity(real_settings):
    with published_connection(real_settings) as connection:
        assert connection.execute("SELECT count(*) FROM analytics.dim_issuer").fetchone()[0] == 8
        for issuer in real_settings.issuers:
            dynamic = canonical_facts(connection, issuer["cik"], AS_OF)
            materialized = connection.execute(
                "SELECT fact_id FROM analytics.stg_canonical_facts WHERE cik=?", [issuer["cik"]]
            ).fetchall()
            assert {f["fact_id"] for f in dynamic} == {row[0] for row in materialized}
        assert (
            connection.execute(
                "SELECT min(available_metrics) FROM analytics.fct_annual_financials"
            ).fetchone()[0]
            >= 5
        )
        assert (
            connection.execute(
                "SELECT count(*) FROM raw.facts WHERE filed > period_end"
            ).fetchone()[0]
            > 100
        )
