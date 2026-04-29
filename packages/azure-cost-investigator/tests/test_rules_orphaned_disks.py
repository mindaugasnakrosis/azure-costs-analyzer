from __future__ import annotations

from azure_cost_investigator.rules import orphaned_disks
from azure_cost_investigator.rules.base import RuleContext
from azure_investigator_core.schema import Confidence, Severity

DISKS = [
    {
        "id": "/sub/disks/orphan-1",
        "name": "orphan-1",
        "location": "uksouth",
        "diskState": "Unattached",
        "managedBy": None,
        "diskSizeGB": 128,
        "sku": {"name": "Premium_LRS", "tier": "Premium"},
        "timeCreated": "2025-12-01T00:00:00Z",
    },
    {
        "id": "/sub/disks/orphan-2",
        "name": "orphan-2",
        "location": "uksouth",
        "diskState": "Reserved",
        "managedBy": None,
        "diskSizeGB": 64,
        "sku": {"name": "StandardSSD_LRS", "tier": "Standard"},
    },
    {
        "id": "/sub/disks/attached",
        "name": "attached",
        "location": "uksouth",
        "diskState": "Attached",
        "managedBy": "/sub/vms/vm-1",
        "diskSizeGB": 256,
        "sku": {"name": "Premium_LRS", "tier": "Premium"},
    },
    {
        # Race condition: state Unattached but managedBy populated → not orphan
        "id": "/sub/disks/edge",
        "name": "edge",
        "location": "uksouth",
        "diskState": "Unattached",
        "managedBy": "/sub/vms/vm-2",
        "diskSizeGB": 32,
        "sku": {"name": "Premium_LRS", "tier": "Premium"},
    },
]


def test_flags_only_orphaned_disks(snapshot_factory, cost_knowledge):
    paths = snapshot_factory({"sub-1": {"disks": DISKS}})
    ctx = RuleContext.from_snapshot(paths, cost_knowledge)

    findings = list(orphaned_disks.evaluate(ctx))

    titles = [f.title for f in findings]
    assert "Orphaned managed disk: orphan-1" in titles
    assert "Orphaned managed disk: orphan-2" in titles
    assert all("attached" not in t and "edge" not in t for t in titles)
    assert len(findings) == 2


def test_savings_range_uses_sku_band_and_includes_assumption(snapshot_factory, cost_knowledge):
    paths = snapshot_factory({"sub-1": {"disks": [DISKS[0]]}})
    ctx = RuleContext.from_snapshot(paths, cost_knowledge)
    (finding,) = list(orphaned_disks.evaluate(ctx))

    sav = finding.estimated_savings
    assert sav is not None
    # Premium_LRS band is 0.12 – 0.15 GBP/GB-month at 128 GB → 15.36 – 19.20
    assert float(sav.low_gbp_per_month) == 15.36
    assert float(sav.high_gbp_per_month) == 19.20
    assert "Premium_LRS" in sav.assumption
    assert finding.severity == Severity.MEDIUM
    assert finding.confidence == Confidence.HIGH


def test_missing_disks_collector_emits_info_finding(snapshot_factory, cost_knowledge):
    paths = snapshot_factory({"sub-1": {"disks": None}})
    ctx = RuleContext.from_snapshot(paths, cost_knowledge)
    findings = list(orphaned_disks.evaluate(ctx))
    assert len(findings) == 1
    f = findings[0]
    assert f.severity == Severity.INFO
    assert f.evidence["missing_collector"] == "disks"


def test_knowledge_refs_present(cost_knowledge):
    for ref in orphaned_disks.KNOWLEDGE_REFS:
        assert cost_knowledge.has(ref), f"corpus missing {ref}"
