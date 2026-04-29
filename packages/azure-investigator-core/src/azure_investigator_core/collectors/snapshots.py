"""Disk snapshots. Age + size drive the old-snapshots rule."""

from __future__ import annotations

from . import CollectorOutput, safe_run_json

NAME = "snapshots"


def collect(subscription_id: str) -> CollectorOutput:
    return safe_run_json(["snapshot", "list", "--subscription", subscription_id])
