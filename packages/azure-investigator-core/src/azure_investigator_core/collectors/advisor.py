"""Azure Advisor cost-category recommendations. Used to cross-validate findings."""

from __future__ import annotations

from . import CollectorOutput, safe_run_json

NAME = "advisor"


def collect(subscription_id: str) -> CollectorOutput:
    return safe_run_json(
        [
            "advisor",
            "recommendation",
            "list",
            "--category",
            "Cost",
            "--subscription",
            subscription_id,
        ]
    )
