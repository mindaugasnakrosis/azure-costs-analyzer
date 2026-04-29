"""App Service plans. `numberOfSites` and `sku.tier` drive the unused-plan rule."""

from __future__ import annotations

from . import CollectorOutput, safe_run_json

NAME = "app_service_plans"


def collect(subscription_id: str) -> CollectorOutput:
    return safe_run_json(["appservice", "plan", "list", "--subscription", subscription_id])
