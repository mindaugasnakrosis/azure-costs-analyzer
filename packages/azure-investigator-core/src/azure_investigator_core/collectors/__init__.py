"""Per-subscription `az` data collectors.

Each module in this package exposes:
- `NAME: str` — canonical collector key (matches filename, used as JSON filename in
  the snapshot folder).
- `collect(subscription_id: str) -> CollectorOutput` — pure function returning data
  or a structured error. Never raises for routine failures (auth/permissions/etc.);
  the orchestrator records the error in the manifest and continues.
"""

from __future__ import annotations

import importlib
from collections.abc import Callable, Iterator
from dataclasses import dataclass
from typing import Any

from ..azcli import AzCliError, AzCliWriteRefused, run_json

# Module names live in __all__; the orchestrator imports each and reads `NAME` +
# `collect`. Adding a collector means listing it here and creating the file.
COLLECTOR_MODULES: tuple[str, ...] = (
    "subscriptions",
    "resources",
    "vms",
    "vm_metrics",
    "disks",
    "public_ips",
    "nics",
    "snapshots",
    "app_service_plans",
    "app_services",
    "sql",
    "storage_accounts",
    "reservations",
    "advisor",
    "consumption",
    "tags",
)


@dataclass(frozen=True)
class CollectorOutput:
    data: Any | None = None
    error: str | None = None
    record_count: int = 0

    @classmethod
    def ok(cls, data: Any) -> CollectorOutput:
        count = len(data) if hasattr(data, "__len__") else 0
        return cls(data=data, record_count=count)

    @classmethod
    def failed(cls, error: str) -> CollectorOutput:
        return cls(error=error)


CollectorFn = Callable[[str], CollectorOutput]


def safe_run_json(args: list[str], *, timeout: float | None = 120.0) -> CollectorOutput:
    """Run a read-only `az` query and convert any failure into a structured error.

    Write-refusals re-raise — they indicate a programmer error in a collector
    (a forbidden verb made it into the args), not a runtime data problem.
    `timeout` is forwarded to the subprocess; pass a larger value for slow
    queries (consumption, vm_metrics, reservations).
    """
    try:
        data = run_json(args, timeout=timeout)
        return CollectorOutput.ok(data if data is not None else [])
    except AzCliWriteRefused:
        raise
    except (AzCliError, ValueError) as e:
        return CollectorOutput.failed(str(e))


def iter_collectors(only: list[str] | None = None) -> Iterator[tuple[str, CollectorFn]]:
    """Yield (name, collect_fn) for each enabled collector."""
    selected = set(only) if only else None
    for mod_name in COLLECTOR_MODULES:
        mod = importlib.import_module(f"{__name__}.{mod_name}")
        name = getattr(mod, "NAME", mod_name)
        if selected is not None and name not in selected:
            continue
        yield name, mod.collect
