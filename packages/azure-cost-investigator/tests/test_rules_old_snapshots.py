from __future__ import annotations

from datetime import UTC, datetime, timedelta

from azure_cost_investigator.rules import old_snapshots
from azure_cost_investigator.rules.base import RuleContext
from azure_investigator_core.schema import Severity


def _snap(name: str, age_days: int, sku: str = "Standard_LRS", size_gb: int = 128):
    created = (datetime.now(UTC) - timedelta(days=age_days)).strftime("%Y-%m-%dT%H:%M:%SZ")
    return {
        "id": f"/sub/snapshots/{name}",
        "name": name,
        "location": "uksouth",
        "sku": {"name": sku},
        "diskSizeGB": size_gb,
        "timeCreated": created,
        "creationData": {"sourceResourceId": "/sub/disks/parent"},
    }


def test_flags_only_snapshots_older_than_threshold(snapshot_factory, cost_knowledge):
    paths = snapshot_factory(
        {
            "sub-1": {
                "snapshots": [
                    _snap("fresh", age_days=10),
                    _snap("aged", age_days=120),
                    _snap("ancient", age_days=400, sku="Premium_LRS", size_gb=512),
                ]
            }
        }
    )
    ctx = RuleContext.from_snapshot(paths, cost_knowledge)
    findings = list(old_snapshots.evaluate(ctx))
    titles = [f.title for f in findings]
    assert any("aged" in t for t in titles)
    assert any("ancient" in t for t in titles)
    assert all("fresh" not in t for t in titles)
    assert len(findings) == 2


def test_premium_snapshot_savings_band_higher_than_standard(snapshot_factory, cost_knowledge):
    paths = snapshot_factory(
        {
            "sub-1": {
                "snapshots": [
                    _snap("std", age_days=200, sku="Standard_LRS", size_gb=100),
                    _snap("prem", age_days=200, sku="Premium_LRS", size_gb=100),
                ]
            }
        }
    )
    ctx = RuleContext.from_snapshot(paths, cost_knowledge)
    fs = {f.evidence["sku"]: f for f in old_snapshots.evaluate(ctx)}
    assert float(fs["Premium_LRS"].estimated_savings.low_gbp_per_month) > float(
        fs["Standard_LRS"].estimated_savings.low_gbp_per_month
    )
    assert all(f.severity == Severity.MEDIUM for f in fs.values())


def test_empty_snapshots_emits_nothing(snapshot_factory, cost_knowledge):
    paths = snapshot_factory({"sub-1": {"snapshots": []}})
    ctx = RuleContext.from_snapshot(paths, cost_knowledge)
    assert list(old_snapshots.evaluate(ctx)) == []


def test_missing_collector_emits_info(snapshot_factory, cost_knowledge):
    paths = snapshot_factory({"sub-1": {"snapshots": None}})
    ctx = RuleContext.from_snapshot(paths, cost_knowledge)
    findings = list(old_snapshots.evaluate(ctx))
    assert len(findings) == 1
    assert findings[0].severity == Severity.INFO


def test_knowledge_refs_present(cost_knowledge):
    for ref in old_snapshots.KNOWLEDGE_REFS:
        assert cost_knowledge.has(ref)
