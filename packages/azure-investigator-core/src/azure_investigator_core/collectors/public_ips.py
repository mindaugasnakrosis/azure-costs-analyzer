"""Public IP addresses. `ipConfiguration` null implies orphan."""

from __future__ import annotations

from . import CollectorOutput, safe_run_json

NAME = "public_ips"


def collect(subscription_id: str) -> CollectorOutput:
    return safe_run_json(["network", "public-ip", "list", "--subscription", subscription_id])
