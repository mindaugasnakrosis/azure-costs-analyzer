from __future__ import annotations

from azure_cost_investigator.rules import stopped_not_deallocated_vms as rule
from azure_cost_investigator.rules.base import RuleContext
from azure_investigator_core.schema import Severity

VMS = [
    {
        "id": "/sub/vms/stopped",
        "name": "stopped",
        "location": "uksouth",
        "powerState": "VM stopped",
        "hardwareProfile": {"vmSize": "Standard_D4s_v5"},
        "tags": {"env": "prod"},
    },
    {
        "id": "/sub/vms/deallocated",
        "name": "deallocated",
        "location": "uksouth",
        "powerState": "VM deallocated",
        "hardwareProfile": {"vmSize": "Standard_D2s_v5"},
    },
    {
        "id": "/sub/vms/running",
        "name": "running",
        "location": "uksouth",
        "powerState": "VM running",
        "hardwareProfile": {"vmSize": "Standard_E8s_v5"},
    },
]


def test_only_stopped_not_deallocated_flagged(snapshot_factory, cost_knowledge):
    paths = snapshot_factory({"sub-1": {"vms": VMS}})
    ctx = RuleContext.from_snapshot(paths, cost_knowledge)
    findings = list(rule.evaluate(ctx))

    assert len(findings) == 1
    f = findings[0]
    assert f.title == "VM stopped but not deallocated: stopped"
    assert f.severity == Severity.CRITICAL
    assert f.evidence["vmSize"] == "Standard_D4s_v5"
    assert f.estimated_savings is not None
    assert f.estimated_savings.assumption.startswith("Assumes")


def test_missing_vms_collector_emits_info(snapshot_factory, cost_knowledge):
    paths = snapshot_factory({"sub-1": {"vms": None}})
    ctx = RuleContext.from_snapshot(paths, cost_knowledge)
    findings = list(rule.evaluate(ctx))
    assert len(findings) == 1
    assert findings[0].severity == Severity.INFO


def test_knowledge_refs_present(cost_knowledge):
    for ref in rule.KNOWLEDGE_REFS:
        assert cost_knowledge.has(ref)
