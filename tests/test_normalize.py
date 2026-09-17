import json
from decimal import Decimal

import pytest

from creditlake.normalize import ContractError, normalize


def test_duplicate_facts_are_deterministic(source):
    observations = source["facts"]["us-gaap"]["Assets"]["units"]["USD"]
    observations.append(observations[0].copy())
    _, first, rejected, telemetry = normalize(json.dumps(source).encode(), 1, 2015)
    _, second, _, _ = normalize(json.dumps(source).encode(), 1, 2015)
    assert first == second
    assert len(first) == 10
    assert not rejected
    assert telemetry["duplicate_source_rows"] == 1


def test_decimal_is_exact():
    data = b'{"cik":1,"entityName":"Test","facts":{"us-gaap":{"Assets":{"units":{"USD":[{"val":123456789012345.125,"end":"2023-12-31","filed":"2024-02-01","accn":"0000000001-24-000001","form":"10-K"}]}}}}}'
    _, facts, _, _ = normalize(data, 1, 2015)
    assert Decimal(facts[0]["value"]) == Decimal("123456789012345.125")


@pytest.mark.parametrize(
    "field,value",
    [
        ("val", True),
        ("val", "100"),
        ("val", -1),
        ("filed", "2023-01-01"),
        ("accn", "bad-id"),
        ("end", "2023-02-31"),
    ],
)
def test_bad_observation_is_quarantined(source, field, value):
    source["facts"]["us-gaap"]["Assets"]["units"]["USD"][0][field] = value
    _, facts, rejected, _ = normalize(json.dumps(source).encode(), 1, 2015)
    assert len(rejected) == 1
    assert all(row["metric"] != "assets" for row in facts)


def test_negative_income_is_valid(source):
    source["facts"]["us-gaap"]["NetIncomeLoss"]["units"]["USD"][0]["val"] = -50
    _, facts, rejected, _ = normalize(json.dumps(source).encode(), 1, 2015)
    assert not rejected
    assert next(row for row in facts if row["metric"] == "net_income")["value"] == "-50"


def test_additive_drift_is_recorded(source):
    taxonomy = source["facts"]["us-gaap"]
    taxonomy["Assets"]["units"]["USD"][0]["future_attribute"] = "new"
    taxonomy["UnknownNewConcept"] = {"units": {"USD": []}}
    _, facts, _, telemetry = normalize(json.dumps(source).encode(), 1, 2015)
    assert len(facts) == 10
    assert telemetry["extra_fact_keys"] == ["future_attribute"]
    assert telemetry["unknown_concepts"] == ["UnknownNewConcept"]


@pytest.mark.parametrize("payload", [b"{}", b"not-json", b'{"cik":2}'])
def test_breaking_source_contract_fails(payload):
    with pytest.raises(ContractError):
        normalize(payload, 1, 2015)
