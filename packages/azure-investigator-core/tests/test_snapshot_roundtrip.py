from __future__ import annotations

import json
from datetime import UTC, datetime

import pytest
from azure_investigator_core.schema import (
    CollectorResult,
    SnapshotManifest,
    SubscriptionRef,
)
from azure_investigator_core.snapshot import (
    init_snapshot,
    latest_snapshot,
    list_snapshots,
    new_snapshot_id,
    read_collector_payload,
    read_manifest,
    resolve_snapshot_id,
    write_collector_errors,
    write_collector_payload,
    write_manifest,
)


def _manifest(snapshot_id: str) -> SnapshotManifest:
    now = datetime.now(UTC)
    return SnapshotManifest(
        snapshot_id=snapshot_id,
        started_at=now,
        finished_at=now,
        identity="me@example.com",
        subscriptions=[SubscriptionRef(id="sub-1", name="TEST")],
        collectors_run=["vms", "disks"],
        collector_results=[
            CollectorResult(
                collector="vms",
                subscription_id="sub-1",
                status="ok",
                record_count=3,
                started_at=now,
                finished_at=now,
            ),
            CollectorResult(
                collector="disks",
                subscription_id="sub-1",
                status="error",
                error="permission denied",
                started_at=now,
                finished_at=now,
            ),
        ],
    )


def test_init_creates_layout(tmp_path):
    paths = init_snapshot(tmp_path, "2026-04-29T10-00-00Z")
    assert paths.base.is_dir()
    assert paths.subscriptions_dir.is_dir()
    assert paths.pricing_dir.is_dir()


def test_manifest_roundtrip(tmp_path):
    paths = init_snapshot(tmp_path, "2026-04-29T10-00-00Z")
    m = _manifest(paths.snapshot_id)
    write_manifest(paths, m)
    reloaded = read_manifest(paths)
    assert reloaded.snapshot_id == m.snapshot_id
    assert len(reloaded.collector_results) == 2
    assert reloaded.collectors_for("sub-1") == {"vms"}


def test_collector_payload_roundtrip(tmp_path):
    paths = init_snapshot(tmp_path, "s1")
    payload = [{"id": "vm-1", "powerState": "running"}]
    write_collector_payload(paths, "sub-1", "vms", payload)
    assert read_collector_payload(paths, "sub-1", "vms") == payload


def test_collector_errors_only_writes_errors(tmp_path):
    paths = init_snapshot(tmp_path, "s1")
    m = _manifest(paths.snapshot_id)
    write_collector_errors(paths, "sub-1", m.collector_results)
    data = json.loads(paths.collector_errors_path("sub-1").read_text())
    assert len(data) == 1
    assert data[0]["collector"] == "disks"


def test_list_and_latest(tmp_path):
    for sid in ["2026-04-29T10-00-00Z", "2026-04-29T11-00-00Z"]:
        paths = init_snapshot(tmp_path, sid)
        write_manifest(paths, _manifest(sid))
    assert list_snapshots(tmp_path) == [
        "2026-04-29T10-00-00Z",
        "2026-04-29T11-00-00Z",
    ]
    assert latest_snapshot(tmp_path) == "2026-04-29T11-00-00Z"


def test_resolve_snapshot_id(tmp_path):
    sid = "2026-04-29T12-00-00Z"
    paths = init_snapshot(tmp_path, sid)
    write_manifest(paths, _manifest(sid))
    assert resolve_snapshot_id(tmp_path, "latest") == sid
    assert resolve_snapshot_id(tmp_path, sid) == sid
    with pytest.raises(FileNotFoundError):
        resolve_snapshot_id(tmp_path, "missing")


def test_resolve_latest_no_snapshots(tmp_path):
    with pytest.raises(FileNotFoundError):
        resolve_snapshot_id(tmp_path, "latest")


def test_new_snapshot_id_format():
    sid = new_snapshot_id()
    assert sid.endswith("Z")
    assert len(sid) == len("2026-04-29T10-00-00Z")
