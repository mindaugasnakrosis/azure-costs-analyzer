"""Tests for the analyse-layer resource-overlap dedup pass.

When `idle_vms` and `oversized_vms` both fire for the same VM, the oversized
finding is suppressed: deallocate is the higher-impact action, and the pair
would otherwise inflate both the triage list and the £/mo headline.
"""

from __future__ import annotations

from decimal import Decimal

from azure_cost_investigator.analyse import _dedup_resource_overlaps
from azure_investigator_core.schema import Confidence, Finding, SavingsRange, Severity


def _f(rule_id: str, *, resource_id: str, sub_id: str = "sub-1", high: int = 100) -> Finding:
    return Finding(
        rule_id=rule_id,
        title=f"{rule_id} {resource_id}",
        subscription_id=sub_id,
        subscription_name="x",
        severity=Severity.MEDIUM,
        confidence=Confidence.MEDIUM,
        knowledge_refs=["vm-rightsizing-thresholds.md", "azure-advisor-cost-rules.md"],
        resource_id=resource_id,
        resource_name=resource_id.rsplit("/", 1)[-1],
        estimated_savings=SavingsRange(
            low_gbp_per_month=Decimal("10"),
            high_gbp_per_month=Decimal(str(high)),
            assumption="t",
        ),
        recommended_investigation="x",
    )


def test_oversized_dropped_when_idle_fires_on_same_vm():
    idle = _f("idle_vms", resource_id="/vm/A", high=130)
    oversized = _f("oversized_vms", resource_id="/vm/A", high=78)
    out = _dedup_resource_overlaps([idle, oversized])
    rule_ids = {f.rule_id for f in out}
    assert rule_ids == {"idle_vms"}


def test_idle_kept_finding_carries_suppression_note():
    idle = _f("idle_vms", resource_id="/vm/A", high=130)
    oversized = _f("oversized_vms", resource_id="/vm/A", high=78)
    (kept,) = _dedup_resource_overlaps([idle, oversized])
    assert "oversized-VM check also flagged" in kept.recommended_investigation
    assert "deallocate is the higher-impact action" in kept.recommended_investigation


def test_oversized_alone_is_kept():
    # No idle finding for the same VM → oversized is the only signal we have,
    # so it must survive the dedup pass.
    oversized = _f("oversized_vms", resource_id="/vm/B", high=78)
    out = _dedup_resource_overlaps([oversized])
    assert [f.rule_id for f in out] == ["oversized_vms"]
    assert "suppressed" not in out[0].recommended_investigation


def test_idle_alone_is_kept_without_note():
    # Idle alone: no suppression note appended.
    idle = _f("idle_vms", resource_id="/vm/B", high=130)
    (kept,) = _dedup_resource_overlaps([idle])
    assert kept.rule_id == "idle_vms"
    assert "oversized-VM check" not in kept.recommended_investigation


def test_dedup_is_per_subscription_and_per_resource():
    # The same resource_id in two subscriptions must dedup independently.
    a_idle = _f("idle_vms", resource_id="/vm/A", sub_id="sub-1", high=130)
    a_over = _f("oversized_vms", resource_id="/vm/A", sub_id="sub-1", high=78)
    b_over = _f("oversized_vms", resource_id="/vm/A", sub_id="sub-2", high=78)
    out = _dedup_resource_overlaps([a_idle, a_over, b_over])
    by_sub = {(f.subscription_id, f.rule_id) for f in out}
    assert by_sub == {("sub-1", "idle_vms"), ("sub-2", "oversized_vms")}


def test_dedup_does_not_collapse_other_rule_pairs():
    # Two unrelated rules on the same resource (e.g. orphaned_disks and
    # untagged_costly_resources) must not be collapsed by this pass — only
    # the idle/oversized pair is editorially equivalent.
    a = _f("orphaned_disks", resource_id="/disk/A", high=20)
    b = _f("untagged_costly_resources", resource_id="/disk/A", high=20)
    out = _dedup_resource_overlaps([a, b])
    assert {f.rule_id for f in out} == {"orphaned_disks", "untagged_costly_resources"}


def test_findings_without_resource_id_are_passed_through():
    # Subscription-level findings (e.g. legacy_storage_redundancy with a
    # null resource_id) must not interact with the dedup pass.
    f = Finding(
        rule_id="dev_skus_in_prod",
        title="x",
        subscription_id="sub-1",
        subscription_name="x",
        severity=Severity.LOW,
        confidence=Confidence.HIGH,
        knowledge_refs=["azure-advisor-cost-rules.md"],
        recommended_investigation="x",
    )
    (out,) = _dedup_resource_overlaps([f])
    assert out is f
