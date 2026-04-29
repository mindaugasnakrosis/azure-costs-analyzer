"""Snapshot filesystem layout: read/write helpers and manifest persistence."""

from __future__ import annotations

import json
from collections.abc import Iterable
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import yaml

from .schema import (
    CollectorResult,
    SnapshotManifest,
    SnapshotPaths,
)

SNAPSHOT_ID_FORMAT = "%Y-%m-%dT%H-%M-%SZ"


def new_snapshot_id(now: datetime | None = None) -> str:
    now = now or datetime.now(UTC)
    return now.strftime(SNAPSHOT_ID_FORMAT)


def paths_for(snapshot_root: Path, snapshot_id: str) -> SnapshotPaths:
    return SnapshotPaths(root=snapshot_root, snapshot_id=snapshot_id)


def init_snapshot(snapshot_root: Path, snapshot_id: str | None = None) -> SnapshotPaths:
    """Create the directory tree for a new snapshot. Returns the paths helper."""
    snapshot_id = snapshot_id or new_snapshot_id()
    p = paths_for(snapshot_root, snapshot_id)
    p.base.mkdir(parents=True, exist_ok=True)
    p.subscriptions_dir.mkdir(parents=True, exist_ok=True)
    p.pricing_dir.mkdir(parents=True, exist_ok=True)
    return p


def write_manifest(paths: SnapshotPaths, manifest: SnapshotManifest) -> Path:
    paths.base.mkdir(parents=True, exist_ok=True)
    payload = manifest.model_dump(mode="json")
    with paths.manifest_path.open("w", encoding="utf-8") as fh:
        yaml.safe_dump(payload, fh, sort_keys=False)
    return paths.manifest_path


def read_manifest(paths: SnapshotPaths) -> SnapshotManifest:
    with paths.manifest_path.open("r", encoding="utf-8") as fh:
        data = yaml.safe_load(fh)
    return SnapshotManifest.model_validate(data)


def write_collector_payload(
    paths: SnapshotPaths, subscription_id: str, collector: str, payload: Any
) -> Path:
    target = paths.collector_path(subscription_id, collector)
    target.parent.mkdir(parents=True, exist_ok=True)
    with target.open("w", encoding="utf-8") as fh:
        json.dump(payload, fh, indent=2, default=str)
    return target


def read_collector_payload(paths: SnapshotPaths, subscription_id: str, collector: str) -> Any:
    target = paths.collector_path(subscription_id, collector)
    if not target.exists():
        return None
    with target.open("r", encoding="utf-8") as fh:
        return json.load(fh)


def write_collector_errors(
    paths: SnapshotPaths,
    subscription_id: str,
    errors: Iterable[CollectorResult],
) -> Path:
    target = paths.collector_errors_path(subscription_id)
    target.parent.mkdir(parents=True, exist_ok=True)
    payload = [e.model_dump(mode="json") for e in errors if e.status == "error"]
    with target.open("w", encoding="utf-8") as fh:
        json.dump(payload, fh, indent=2, default=str)
    return target


def list_snapshots(snapshot_root: Path) -> list[str]:
    if not snapshot_root.exists():
        return []
    return sorted(
        p.name for p in snapshot_root.iterdir() if p.is_dir() and (p / "manifest.yaml").exists()
    )


def latest_snapshot(snapshot_root: Path) -> str | None:
    snaps = list_snapshots(snapshot_root)
    return snaps[-1] if snaps else None


def resolve_snapshot_id(snapshot_root: Path, ref: str) -> str:
    """Accept 'latest' or an explicit id; return the id or raise."""
    if ref == "latest":
        sid = latest_snapshot(snapshot_root)
        if sid is None:
            raise FileNotFoundError(
                f"No snapshots found under {snapshot_root}. Run `azure-investigator pull` first."
            )
        return sid
    if not (snapshot_root / ref / "manifest.yaml").exists():
        raise FileNotFoundError(f"Snapshot {ref!r} not found under {snapshot_root}.")
    return ref
