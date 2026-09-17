import copy
import json
import shutil
from datetime import date
from pathlib import Path

import pytest

from creditlake.config import Settings
from creditlake.pipeline import release_manifest, run_pipeline
from creditlake.warehouse import connect

ROOT = Path(__file__).resolve().parents[1]
AS_OF = date(2026, 9, 17)


def observation(
    value,
    *,
    end="2023-12-31",
    start=None,
    filed="2024-02-15",
    accession="0000000001-24-000001",
    form="10-K",
):
    row = {
        "val": value,
        "end": end,
        "filed": filed,
        "accn": accession,
        "form": form,
        "fy": 2023,
        "fp": "FY",
    }
    if start:
        row["start"] = start
    return row


def payload():
    concepts = {
        "RevenueFromContractWithCustomerExcludingAssessedTax": (1000, "2023-01-01"),
        "NetIncomeLoss": (100, "2023-01-01"),
        "OperatingIncomeLoss": (140, "2023-01-01"),
        "NetCashProvidedByUsedInOperatingActivities": (120, "2023-01-01"),
        "Assets": (2000, None),
        "Liabilities": (1200, None),
        "StockholdersEquity": (800, None),
        "AssetsCurrent": (600, None),
        "LiabilitiesCurrent": (300, None),
        "CashAndCashEquivalentsAtCarryingValue": (200, None),
    }
    return {
        "cik": 1,
        "entityName": "Test Issuer",
        "facts": {
            "us-gaap": {
                tag: {"units": {"USD": [observation(value, start=start)]}}
                for tag, (value, start) in concepts.items()
            }
        },
    }


def fetcher(source):
    def fetch(cik):
        assert cik == 1
        return json.dumps(source).encode(), "https://data.sec.gov/test-only-fixture"

    return fetch


@pytest.fixture
def source():
    return copy.deepcopy(payload())


@pytest.fixture(scope="session")
def real_settings(tmp_path_factory):
    settings = Settings.load(ROOT, tmp_path_factory.mktemp("real-data"))
    run_pipeline(settings, as_of=AS_OF)
    return settings


@pytest.fixture(scope="session")
def base_synthetic(tmp_path_factory):
    root = tmp_path_factory.mktemp("synthetic-project")
    shutil.copytree(ROOT / "dbt", root / "dbt")
    (root / "config").mkdir()
    (root / "config" / "issuers.json").write_text(
        json.dumps(
            [{"cik": 1, "ticker": "TEST", "sector": "Testing", "headquarters": "Dallas, TX"}]
        )
    )
    settings = Settings.load(root, root / "data")
    run_pipeline(settings, as_of=AS_OF, source_fetcher=fetcher(payload()))
    return settings


@pytest.fixture
def synthetic_settings(base_synthetic, tmp_path):
    root = tmp_path / "project"
    shutil.copytree(base_synthetic.root, root)
    return Settings.load(root, root / "data")


def published_connection(settings):
    manifest = release_manifest(settings.data_dir)
    return connect(settings.data_dir / manifest["warehouse"], read_only=True)
