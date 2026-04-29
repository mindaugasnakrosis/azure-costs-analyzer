"""Subscription metadata. Only `subscription_id` is meaningful — this collector
records the subscription as the orchestrator sees it (state, tenant, name)."""

from __future__ import annotations

from . import CollectorOutput, safe_run_json

NAME = "subscriptions"


def collect(subscription_id: str) -> CollectorOutput:
    out = safe_run_json(["account", "show", "--subscription", subscription_id])
    if out.error or out.data is None:
        return out
    return CollectorOutput.ok([out.data])
