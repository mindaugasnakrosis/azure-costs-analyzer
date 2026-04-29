"""Rule registry. Each rule module exports `RULE_ID`, `KNOWLEDGE_REFS`, and a
top-level `evaluate(ctx) -> Iterable[Finding]` function. The registry imports
modules lazily — adding a rule is a one-line append to `RULE_MODULES`.
"""

from __future__ import annotations

import importlib
from collections.abc import Iterable

from .base import RuleContext

RULE_MODULES: tuple[str, ...] = (
    "orphaned_disks",
    "unattached_public_ips",
    "stopped_not_deallocated_vms",
    "idle_vms",
    "oversized_vms",
    "unused_app_service_plans",
    "old_snapshots",
    "underused_reservations",
    "dev_skus_in_prod",
    "untagged_costly_resources",
    "legacy_storage_redundancy",
)


def iter_rules(only: Iterable[str] | None = None, exclude: Iterable[str] | None = None):
    """Yield (rule_id, knowledge_refs, evaluate_fn) for each enabled rule."""
    selected = set(only) if only else None
    excluded = set(exclude) if exclude else set()
    for mod_name in RULE_MODULES:
        try:
            mod = importlib.import_module(f"{__name__}.{mod_name}")
        except ImportError:
            continue
        rule_id = getattr(mod, "RULE_ID", mod_name)
        if selected is not None and rule_id not in selected:
            continue
        if rule_id in excluded:
            continue
        evaluate = getattr(mod, "evaluate", None)
        if evaluate is None:
            continue
        knowledge_refs = list(getattr(mod, "KNOWLEDGE_REFS", []))
        yield rule_id, knowledge_refs, evaluate


__all__ = ["RuleContext", "iter_rules", "RULE_MODULES"]
