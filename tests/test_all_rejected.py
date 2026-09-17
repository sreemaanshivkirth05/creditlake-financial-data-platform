import json

import pytest
from conftest import AS_OF, fetcher

from creditlake.normalize import ContractError
from creditlake.pipeline import release_manifest, run_pipeline


def test_all_invalid_rows_are_preserved_in_quarantine(synthetic_settings, source):
    before = release_manifest(synthetic_settings.data_dir)
    for definition in source["facts"]["us-gaap"].values():
        definition["units"]["USD"][0]["val"] = "not-a-number"
    with pytest.raises(ContractError, match="No supported financial facts"):
        run_pipeline(synthetic_settings, as_of=AS_OF, source_fetcher=fetcher(source))
    assert release_manifest(synthetic_settings.data_dir) == before
    quarantined = list((synthetic_settings.data_dir / "quarantine").rglob("*.json"))
    assert len(quarantined) == 1
    assert len(json.loads(quarantined[0].read_text())) == 10
