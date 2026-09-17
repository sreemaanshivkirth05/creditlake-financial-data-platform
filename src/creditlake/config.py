from __future__ import annotations

import json
import os
from dataclasses import dataclass
from pathlib import Path

NORMALIZER_VERSION = "1"

# Ordered fallbacks are explicit, reviewable financial metric contracts.
# These are whole-entity USD metrics; custom and segment taxonomies are out of scope.
METRICS = {
    "revenue": (
        "duration",
        [
            "RevenueFromContractWithCustomerExcludingAssessedTax",
            "Revenues",
            "SalesRevenueNet",
            "RevenueFromContractWithCustomerIncludingAssessedTax",
        ],
    ),
    "net_income": ("duration", ["NetIncomeLoss", "ProfitLoss"]),
    "operating_income": ("duration", ["OperatingIncomeLoss"]),
    "operating_cash_flow": ("duration", ["NetCashProvidedByUsedInOperatingActivities"]),
    "assets": ("instant", ["Assets"]),
    "liabilities": ("instant", ["Liabilities"]),
    "equity": (
        "instant",
        [
            "StockholdersEquityIncludingPortionAttributableToNoncontrollingInterest",
            "StockholdersEquity",
        ],
    ),
    "current_assets": ("instant", ["AssetsCurrent"]),
    "current_liabilities": ("instant", ["LiabilitiesCurrent"]),
    "cash": ("instant", ["CashAndCashEquivalentsAtCarryingValue"]),
}


@dataclass(frozen=True)
class Settings:
    root: Path
    data_dir: Path
    min_year: int = 2015

    @classmethod
    def load(
        cls, root: Path | None = None, data_dir: Path | None = None, min_year: int = 2015
    ) -> Settings:
        # Installed wheel users can point CREDITLAKE_ROOT at the unpacked project.
        default_root = Path(__file__).resolve().parents[2]
        project_root = (root or Path(os.getenv("CREDITLAKE_ROOT", str(default_root)))).resolve()
        storage = (
            data_dir or Path(os.getenv("CREDITLAKE_DATA_DIR", str(project_root / "data")))
        ).resolve()
        if not 2009 <= min_year <= 2099:
            raise ValueError("min_year must be between 2009 and 2099")
        return cls(project_root, storage, min_year)

    @property
    def issuers(self) -> list[dict]:
        issuers = json.loads((self.root / "config" / "issuers.json").read_text())
        ciks = [row["cik"] for row in issuers]
        if len(ciks) != len(set(ciks)):
            raise ValueError("Issuer CIKs must be unique")
        for issuer in issuers:
            if type(issuer["cik"]) is not int or not 1 <= issuer["cik"] < 10**10:
                raise ValueError("Invalid issuer CIK")
        return issuers
