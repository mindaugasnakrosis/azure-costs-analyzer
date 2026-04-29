"""Subscription-scope tag inventory (distinct keys + values used)."""

from __future__ import annotations

from . import CollectorOutput, safe_run_json

NAME = "tags"


def collect(subscription_id: str) -> CollectorOutput:
    return safe_run_json(["tag", "list", "--subscription", subscription_id])
