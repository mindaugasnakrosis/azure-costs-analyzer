"""Web apps / function apps."""

from __future__ import annotations

from . import CollectorOutput, safe_run_json

NAME = "app_services"


def collect(subscription_id: str) -> CollectorOutput:
    return safe_run_json(["webapp", "list", "--subscription", subscription_id])
