"""All resources in the subscription. Coarse but invaluable for cross-rule
queries (e.g. flagging untagged costly resources without re-pulling specific
resource families)."""

from __future__ import annotations

from . import CollectorOutput, safe_run_json

NAME = "resources"


def collect(subscription_id: str) -> CollectorOutput:
    return safe_run_json(["resource", "list", "--subscription", subscription_id])
