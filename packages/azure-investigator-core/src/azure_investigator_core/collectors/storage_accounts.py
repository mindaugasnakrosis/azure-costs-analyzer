"""Storage accounts. SKU tier (LRS/GRS/RA-GRS/GZRS) drives the legacy-redundancy rule."""

from __future__ import annotations

from . import CollectorOutput, safe_run_json

NAME = "storage_accounts"


def collect(subscription_id: str) -> CollectorOutput:
    return safe_run_json(["storage", "account", "list", "--subscription", subscription_id])
