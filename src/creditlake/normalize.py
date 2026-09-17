from __future__ import annotations

import hashlib
import json
import re
from datetime import date
from decimal import Decimal, InvalidOperation

from creditlake.config import METRICS

CONCEPTS = {
    concept: (metric, kind, priority)
    for metric, (kind, aliases) in METRICS.items()
    for priority, concept in enumerate(aliases)
}
EXPECTED_KEYS = {"start", "end", "val", "accn", "fy", "fp", "form", "filed", "frame"}


class ContractError(ValueError):
    def __init__(self, message, *, rejected=None, telemetry=None):
        super().__init__(message)
        self.rejected = rejected or []
        self.telemetry = telemetry or {}


def digest(value) -> str:
    return hashlib.sha256(
        json.dumps(value, sort_keys=True, default=str, separators=(",", ":")).encode()
    ).hexdigest()


def parse_date(value) -> date:
    if not isinstance(value, str) or not re.fullmatch(r"\d{4}-\d{2}-\d{2}", value):
        raise ValueError("Date must use YYYY-MM-DD")
    return date.fromisoformat(value)


def normalize(
    data: bytes, expected_cik: int, min_year: int
) -> tuple[dict, list[dict], list[dict], dict]:
    """Return entity, accepted facts, rejected facts, and schema telemetry.

    Every source fact's natural key includes concept, period, unit, filing,
    and value. Different filings and changed values survive deduplication.
    No financial values are imputed, annualized, or scaled.
    """
    try:
        payload = json.loads(data, parse_float=Decimal)
        if type(payload["cik"]) is not int or payload["cik"] != expected_cik:
            raise ContractError("Source CIK does not match requested issuer")
        if not isinstance(payload["entityName"], str) or not payload["entityName"].strip():
            raise ContractError("Missing entityName")
        taxonomy = payload["facts"]["us-gaap"]
        if not isinstance(taxonomy, dict):
            raise ContractError("us-gaap must be a concept map")
    except (KeyError, TypeError, json.JSONDecodeError) as exc:
        raise ContractError(f"Source envelope violates SEC contract: {exc}") from exc

    accepted, rejected, seen = [], [], set()
    telemetry = {
        "unknown_concepts": [],
        "extra_fact_keys": [],
        "ignored_non_usd": 0,
        "ignored_old_periods": 0,
        "duplicate_source_rows": 0,
    }
    extra_keys = set()
    for concept, definition in taxonomy.items():
        if concept not in CONCEPTS:
            telemetry["unknown_concepts"].append(concept)
            continue
        metric, kind, priority = CONCEPTS[concept]
        try:
            units = definition["units"]
            observations = units.get("USD", [])
            if not isinstance(units, dict) or not isinstance(observations, list):
                raise TypeError("units must be a map of fact arrays")
            telemetry["ignored_non_usd"] += sum(len(v) for k, v in units.items() if k != "USD")
        except (KeyError, TypeError, AttributeError) as exc:
            raise ContractError(f"Invalid concept shape: {concept}") from exc
        for index, fact in enumerate(observations):
            try:
                if not isinstance(fact, dict):
                    raise ValueError("Fact must be an object")
                extra_keys.update(set(fact) - EXPECTED_KEYS)
                end = parse_date(fact["end"])
                if end.year < min_year:
                    telemetry["ignored_old_periods"] += 1
                    continue
                filed = parse_date(fact["filed"])
                start = parse_date(fact["start"]) if kind == "duration" else None
                if start and start > end:
                    raise ValueError("Period start is later than period end")
                if filed < end:
                    raise ValueError("Filing predates the reported period end")
                if not re.fullmatch(r"\d{10}-\d{2}-\d{6}", fact["accn"]):
                    raise ValueError("Invalid accession number")
                if not isinstance(fact["form"], str):
                    raise ValueError("Missing form")
                if isinstance(fact["val"], bool) or not isinstance(
                    fact["val"], (int, float, Decimal)
                ):
                    raise ValueError("Value must be numeric")
                value = Decimal(str(fact["val"]))
                if not value.is_finite() or abs(value) >= Decimal("1e30"):
                    raise ValueError("Value outside decimal contract")
                if value.as_tuple().exponent < -4:
                    raise ValueError("USD value exceeds four fractional digits")
                if (
                    metric
                    in {
                        "assets",
                        "liabilities",
                        "current_assets",
                        "current_liabilities",
                        "cash",
                        "revenue",
                    }
                    and value < 0
                ):
                    raise ValueError("Negative value for a nonnegative metric")
                value_text = format(value, "f")
                if "." in value_text:
                    value_text = value_text.rstrip("0").rstrip(".")
                if value == 0:
                    value_text = "0"
                row = {
                    "cik": expected_cik,
                    "metric": metric,
                    "concept": concept,
                    "kind": kind,
                    "alias_priority": priority,
                    "unit": "USD",
                    "period_start": start.isoformat() if start else None,
                    "period_end": end.isoformat(),
                    "value": value_text,
                    "accession": fact["accn"],
                    "form": fact["form"],
                    "filed": filed.isoformat(),
                    "fiscal_year_hint": fact.get("fy"),
                    "fiscal_period_hint": fact.get("fp"),
                }
                # fy/fp belong to the filing, not necessarily the economic period.
                # They are retained as source hints and never determine annual grain.
                row["fact_id"] = digest(
                    {
                        k: row[k]
                        for k in (
                            "cik",
                            "concept",
                            "unit",
                            "period_start",
                            "period_end",
                            "value",
                            "accession",
                            "form",
                            "filed",
                        )
                    }
                )
                if row["fact_id"] in seen:
                    telemetry["duplicate_source_rows"] += 1
                    continue
                seen.add(row["fact_id"])
                accepted.append(row)
            except (KeyError, ValueError, TypeError, InvalidOperation) as exc:
                rejected.append(
                    {"concept": concept, "index": index, "reason": str(exc), "source_fact": fact}
                )
    telemetry["extra_fact_keys"] = sorted(extra_keys)
    telemetry["unknown_concepts"].sort()
    if not accepted:
        raise ContractError(
            "No supported financial facts survived the source contract",
            rejected=rejected,
            telemetry=telemetry,
        )
    return {"cik": expected_cik, "name": payload["entityName"]}, accepted, rejected, telemetry
