"""Rule protocol + helpers shared by every cost rule.

A *rule* is a callable that takes a `RuleContext` (snapshot view + pricing client +
knowledge corpus) and yields zero or more `Finding`s. Rules are decoupled from
the snapshot loader so they can be unit-tested against synthetic fixtures.
"""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass, field
from decimal import Decimal
from typing import Any, Protocol

from azure_investigator_core.knowledge_loader import KnowledgeCorpus
from azure_investigator_core.pricing import PricingClient
from azure_investigator_core.schema import (
    Confidence,
    Finding,
    SavingsRange,
    Severity,
    SnapshotManifest,
    SubscriptionRef,
)
from azure_investigator_core.snapshot import (
    SnapshotPaths,
    read_collector_payload,
    read_manifest,
)


@dataclass
class RuleContext:
    """Everything a rule needs to evaluate a snapshot.

    `data_for(subscription_id, collector)` returns the parsed JSON payload or
    None if the collector did not run successfully for that subscription.
    """

    paths: SnapshotPaths
    manifest: SnapshotManifest
    knowledge: KnowledgeCorpus
    pricing: PricingClient | None = None
    config: dict[str, Any] = field(default_factory=dict)

    @classmethod
    def from_snapshot(
        cls,
        paths: SnapshotPaths,
        knowledge: KnowledgeCorpus,
        *,
        pricing: PricingClient | None = None,
        config: dict[str, Any] | None = None,
    ) -> RuleContext:
        manifest = read_manifest(paths)
        return cls(
            paths=paths,
            manifest=manifest,
            knowledge=knowledge,
            pricing=pricing,
            config=config or {},
        )

    def subscriptions(self) -> list[SubscriptionRef]:
        return list(self.manifest.subscriptions)

    def has_data(self, subscription_id: str, collector: str) -> bool:
        return self.manifest.has_data(subscription_id, collector)

    def data_for(self, subscription_id: str, collector: str) -> Any | None:
        if not self.has_data(subscription_id, collector):
            return None
        return read_collector_payload(self.paths, subscription_id, collector)


class Rule(Protocol):
    """Rule protocol. Rules ship as modules with `RULE_ID`, `KNOWLEDGE_REFS`, and
    a top-level `evaluate(ctx) -> Iterable[Finding]` callable."""

    RULE_ID: str
    KNOWLEDGE_REFS: list[str]

    def evaluate(self, ctx: RuleContext) -> Iterable[Finding]: ...


# ---- helpers ----------------------------------------------------------------


def info_missing_data(
    *,
    rule_id: str,
    title: str,
    subscription: SubscriptionRef,
    missing_collector: str,
) -> Finding:
    """Build a uniform Info-level finding when a rule's prerequisite collector
    didn't run for a subscription. Severity Info is exempt from the
    knowledge-citation requirement."""
    return Finding(
        rule_id=rule_id,
        title=f"{title} — could not evaluate",
        subscription_id=subscription.id,
        subscription_name=subscription.name,
        severity=Severity.INFO,
        confidence=Confidence.HIGH,
        knowledge_refs=[],
        evidence={"missing_collector": missing_collector},
        recommended_investigation=(
            f"Re-run `azure-investigator pull --subscription {subscription.id} "
            f"--collector {missing_collector}` and re-analyse."
        ),
    )


def savings_range(
    low: Decimal | float | int,
    high: Decimal | float | int,
    assumption: str,
) -> SavingsRange:
    return SavingsRange(
        low_gbp_per_month=Decimal(str(low)),
        high_gbp_per_month=Decimal(str(high)),
        assumption=assumption,
    )
