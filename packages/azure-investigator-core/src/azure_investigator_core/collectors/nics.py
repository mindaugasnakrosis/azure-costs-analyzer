"""Network interfaces — useful when correlating IP/VM associations."""

from __future__ import annotations

from . import CollectorOutput, safe_run_json

NAME = "nics"


def collect(subscription_id: str) -> CollectorOutput:
    return safe_run_json(["network", "nic", "list", "--subscription", subscription_id])
