from __future__ import annotations

from azure_cost_investigator.rules import idle_vms
from azure_cost_investigator.rules.base import RuleContext
from azure_investigator_core.schema import Confidence, Severity
from metric_helpers import metric_record, vm_record


def test_flags_vm_below_p95_threshold(snapshot_factory, cost_knowledge):
    vms = [vm_record(vm_id="/sub/vms/idle", name="idle", sku="Standard_D4s_v5")]
    metrics = [
        metric_record(vm_id="/sub/vms/idle", vm_name="idle", avg_pct=1.5, p95_pct=2.5, max_pct=4.0)
    ]
    paths = snapshot_factory({"sub-1": {"vms": vms, "vm_metrics": metrics}})
    ctx = RuleContext.from_snapshot(paths, cost_knowledge)
    findings = list(idle_vms.evaluate(ctx))
    flagged = [f for f in findings if f.severity == Severity.MEDIUM]
    assert len(flagged) == 1
    f = flagged[0]
    assert f.confidence == Confidence.MEDIUM
    assert f.evidence["p95_cpu_pct"] == 2.5
    assert "outbound-network" in f.estimated_savings.assumption


def test_does_not_flag_above_threshold(snapshot_factory, cost_knowledge):
    vms = [vm_record(vm_id="/sub/vms/busy", name="busy")]
    metrics = [
        metric_record(vm_id="/sub/vms/busy", vm_name="busy", avg_pct=20, p95_pct=45, max_pct=70)
    ]
    paths = snapshot_factory({"sub-1": {"vms": vms, "vm_metrics": metrics}})
    ctx = RuleContext.from_snapshot(paths, cost_knowledge)
    findings = list(idle_vms.evaluate(ctx))
    medium = [f for f in findings if f.severity == Severity.MEDIUM]
    assert medium == []


def test_sparse_metrics_emit_info_not_medium(snapshot_factory, cost_knowledge):
    vms = [vm_record(vm_id="/sub/vms/sparse", name="sparse")]
    metrics = [metric_record(vm_id="/sub/vms/sparse", vm_name="sparse", points=10, avg_pct=1.0)]
    paths = snapshot_factory({"sub-1": {"vms": vms, "vm_metrics": metrics}})
    ctx = RuleContext.from_snapshot(paths, cost_knowledge)
    findings = list(idle_vms.evaluate(ctx))
    assert len(findings) == 1
    assert findings[0].severity == Severity.INFO
    assert findings[0].evidence["datapoints"] == 10
    assert findings[0].evidence["min_required"] == 168


def test_missing_metrics_collector_emits_info_per_subscription(snapshot_factory, cost_knowledge):
    paths = snapshot_factory({"sub-1": {"vms": [], "vm_metrics": None}})
    ctx = RuleContext.from_snapshot(paths, cost_knowledge)
    findings = list(idle_vms.evaluate(ctx))
    assert len(findings) == 1
    assert findings[0].severity == Severity.INFO
    assert findings[0].evidence["missing_collector"] == "vm_metrics"


def test_knowledge_refs_present(cost_knowledge):
    for ref in idle_vms.KNOWLEDGE_REFS:
        assert cost_knowledge.has(ref)
