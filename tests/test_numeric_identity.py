import json

from creditlake.normalize import normalize


def test_equivalent_numeric_representation_does_not_create_another_version(source):
    observations = source["facts"]["us-gaap"]["Assets"]["units"]["USD"]
    duplicate = observations[0].copy()
    duplicate["val"] = 2000.0
    observations.append(duplicate)
    for representation in ["2000.0", "2e3", "2000.0000"]:
        encoded = json.dumps(source).replace('"val": 2000,', f'"val": {representation},', 1)
        _, facts, rejected, telemetry = normalize(encoded.encode(), 1, 2015)
        assert not rejected
        assert len(facts) == 10
        assert telemetry["duplicate_source_rows"] == 1
