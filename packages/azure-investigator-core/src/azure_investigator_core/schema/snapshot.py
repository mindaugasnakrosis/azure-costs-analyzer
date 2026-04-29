from __future__ import annotations

from datetime import datetime
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field


class CollectorResult(BaseModel):
    model_config = ConfigDict(extra="forbid")

    collector: str
    subscription_id: str
    status: Literal["ok", "error", "skipped"]
    record_count: int = 0
    error: str | None = None
    started_at: datetime
    finished_at: datetime


class SubscriptionRef(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: str
    name: str
    tenant_id: str | None = None
    state: str | None = None


class SnapshotManifest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    version: int = 1
    snapshot_id: str
    started_at: datetime
    finished_at: datetime | None = None
    identity: str
    currency: str = "GBP"
    subscriptions: list[SubscriptionRef] = Field(default_factory=list)
    collectors_run: list[str] = Field(default_factory=list)
    collector_results: list[CollectorResult] = Field(default_factory=list)

    def collectors_for(self, subscription_id: str) -> set[str]:
        return {
            r.collector
            for r in self.collector_results
            if r.subscription_id == subscription_id and r.status == "ok"
        }

    def has_data(self, subscription_id: str, collector: str) -> bool:
        return collector in self.collectors_for(subscription_id)


class SnapshotPaths(BaseModel):
    """Filesystem layout helper. All paths derived from a snapshot root + id."""

    model_config = ConfigDict(extra="forbid")

    root: Path
    snapshot_id: str

    @property
    def base(self) -> Path:
        return self.root / self.snapshot_id

    @property
    def manifest_path(self) -> Path:
        return self.base / "manifest.yaml"

    @property
    def subscriptions_dir(self) -> Path:
        return self.base / "subscriptions"

    @property
    def pricing_dir(self) -> Path:
        return self.base / "pricing"

    def subscription_dir(self, subscription_id: str) -> Path:
        return self.subscriptions_dir / subscription_id

    def collector_path(self, subscription_id: str, collector: str) -> Path:
        return self.subscription_dir(subscription_id) / f"{collector}.json"

    def collector_errors_path(self, subscription_id: str) -> Path:
        return self.subscription_dir(subscription_id) / "collector_errors.json"
