"""Snapshot orchestrator.

Iterates the configured set of subscriptions × collectors, writes per-collector
JSON to the snapshot folder, records a manifest with structured per-collector
outcomes. A failure in one collector for one subscription never aborts the rest.
"""

from __future__ import annotations

from collections.abc import Callable
from datetime import UTC, datetime

from .azcli import AzCliError, run_json
from .collectors import CollectorOutput, iter_collectors
from .config import Config
from .schema import (
    CollectorResult,
    SnapshotManifest,
    SubscriptionRef,
)
from .snapshot import (
    SnapshotPaths,
    init_snapshot,
    write_collector_errors,
    write_collector_payload,
    write_manifest,
)

ProgressCb = Callable[[str], None]


def _identity() -> str:
    try:
        data = run_json(["account", "show"])
    except AzCliError:
        return "unknown"
    if not data:
        return "unknown"
    user = data.get("user") or {}
    return user.get("name") or data.get("name") or "unknown"


def _list_subscriptions(
    only: list[str] | None,
    exclude: list[str],
) -> list[SubscriptionRef]:
    data = run_json(["account", "list", "--refresh"])
    if not data:
        return []
    subs: list[SubscriptionRef] = []
    excluded = set(exclude or [])
    selected = set(only) if only else None
    for item in data:
        sid = item.get("id") or item.get("subscriptionId")
        name = item.get("name", "")
        if not sid:
            continue
        if selected is not None and sid not in selected and name not in selected:
            continue
        if sid in excluded or name in excluded:
            continue
        subs.append(
            SubscriptionRef(
                id=sid,
                name=name,
                tenant_id=item.get("tenantId"),
                state=item.get("state"),
            )
        )
    return subs


def pull(
    *,
    config: Config | None = None,
    subscriptions: list[str] | None = None,
    exclude: list[str] | None = None,
    collectors: list[str] | None = None,
    progress: ProgressCb | None = None,
) -> SnapshotPaths:
    """Run a snapshot. Returns the SnapshotPaths of the new snapshot."""
    cfg = config or Config.load()
    paths = init_snapshot(cfg.snapshot_root)
    started_at = datetime.now(UTC)

    say = progress or (lambda _msg: None)
    say(f"snapshot {paths.snapshot_id} → {paths.base}")

    subs = _list_subscriptions(subscriptions, exclude or cfg.excluded_subscriptions)
    if not subs:
        say("warning: no subscriptions selected")

    collector_run_keys: list[str] = []
    results: list[CollectorResult] = []

    for sub in subs:
        say(f"subscription {sub.name} ({sub.id})")
        per_sub_results: list[CollectorResult] = []
        for name, collect_fn in iter_collectors(only=collectors):
            if name not in collector_run_keys:
                collector_run_keys.append(name)
            t0 = datetime.now(UTC)
            try:
                out: CollectorOutput = collect_fn(sub.id)
            except Exception as e:  # noqa: BLE001 — we never want one bad collector to kill the run
                out = CollectorOutput.failed(f"{type(e).__name__}: {e}")
            t1 = datetime.now(UTC)
            if out.error:
                say(f"  ✗ {name}: {out.error[:120]}")
                result = CollectorResult(
                    collector=name,
                    subscription_id=sub.id,
                    status="error",
                    error=out.error,
                    started_at=t0,
                    finished_at=t1,
                )
            else:
                write_collector_payload(paths, sub.id, name, out.data)
                say(f"  ✓ {name} ({out.record_count} records)")
                result = CollectorResult(
                    collector=name,
                    subscription_id=sub.id,
                    status="ok",
                    record_count=out.record_count,
                    started_at=t0,
                    finished_at=t1,
                )
            per_sub_results.append(result)
            results.append(result)
        write_collector_errors(paths, sub.id, per_sub_results)

    finished_at = datetime.now(UTC)
    manifest = SnapshotManifest(
        snapshot_id=paths.snapshot_id,
        started_at=started_at,
        finished_at=finished_at,
        identity=_identity(),
        currency=cfg.currency,
        subscriptions=subs,
        collectors_run=collector_run_keys,
        collector_results=results,
    )
    write_manifest(paths, manifest)
    say(f"manifest written → {paths.manifest_path}")
    return paths
