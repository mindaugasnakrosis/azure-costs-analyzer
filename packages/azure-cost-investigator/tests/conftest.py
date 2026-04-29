"""Shared fixtures: a synthetic in-memory snapshot for rule unit tests."""

from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import pytest
from azure_investigator_core.knowledge_loader import KnowledgeCorpus
from azure_investigator_core.schema import (
    CollectorResult,
    SnapshotManifest,
    SubscriptionRef,
)
from azure_investigator_core.snapshot import (
    init_snapshot,
    write_collector_payload,
    write_manifest,
)


@pytest.fixture
def cost_knowledge() -> KnowledgeCorpus:
    return KnowledgeCorpus.load("azure_cost_investigator")


@pytest.fixture
def snapshot_factory(tmp_path: Path):
    """Build a snapshot on disk from a dict of collectors-per-subscription."""

    def _make(
        per_sub: dict[str, dict[str, Any]],
        *,
        snapshot_id: str = "2026-04-29T10-00-00Z",
    ):
        paths = init_snapshot(tmp_path / "snaps", snapshot_id)
        now = datetime.now(UTC)

        subscriptions: list[SubscriptionRef] = []
        results: list[CollectorResult] = []
        collectors_run: list[str] = []

        for sub_id, collectors in per_sub.items():
            subscriptions.append(SubscriptionRef(id=sub_id, name=f"sub-{sub_id}"))
            for collector, payload in collectors.items():
                if collector not in collectors_run:
                    collectors_run.append(collector)
                if payload is None:
                    results.append(
                        CollectorResult(
                            collector=collector,
                            subscription_id=sub_id,
                            status="error",
                            error="synthetic missing",
                            started_at=now,
                            finished_at=now,
                        )
                    )
                    continue
                write_collector_payload(paths, sub_id, collector, payload)
                results.append(
                    CollectorResult(
                        collector=collector,
                        subscription_id=sub_id,
                        status="ok",
                        record_count=len(payload) if hasattr(payload, "__len__") else 0,
                        started_at=now,
                        finished_at=now,
                    )
                )

        manifest = SnapshotManifest(
            snapshot_id=paths.snapshot_id,
            started_at=now,
            finished_at=now,
            identity="test@example.com",
            currency="GBP",
            subscriptions=subscriptions,
            collectors_run=collectors_run,
            collector_results=results,
        )
        write_manifest(paths, manifest)
        return paths

    return _make
