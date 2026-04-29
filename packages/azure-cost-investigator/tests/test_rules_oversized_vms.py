from __future__ import annotations

from azure_cost_investigator.rules import oversized_vms
from azure_cost_investigator.rules.base import RuleContext
from azure_investigator_core.schema import Confidence, Severity
from metric_helpers import metric_record, vm_record


def test_flags_when_avg_and_p95_below_limits(snapshot_factory, cost_knowledge):
    vms = [vm_record(vm_id="/sub/vms/over", name="over", sku="Standard_D4s_v5")]
    metrics = [
        metric_record(vm_id="/sub/vms/over", vm_name="over", avg_pct=12, p95_pct=18, max_pct=22)
    ]
    paths = snapshot_factory({"sub-1": {"vms": vms, "vm_metrics": metrics}})
    ctx = RuleContext.from_snapshot(paths, cost_knowledge)
    findings = list(oversized_vms.evaluate(ctx))
    flagged = [f for f in findings if f.severity == Severity.MEDIUM]
    assert len(flagged) == 1
    assert flagged[0].confidence == Confidence.LOW
    assert "Memory and outbound-network" in flagged[0].estimated_savings.assumption


def test_does_not_flag_busy_or_idle_burstable(snapshot_factory, cost_knowledge):
    vms = [
        vm_record(vm_id="/busy", name="busy"),
        vm_record(vm_id="/idle-burst", name="idle-burst"),
    ]
    metrics = [
        metric_record(vm_id="/busy", vm_name="busy", avg_pct=35, p95_pct=80, max_pct=95),
        # idle but with a spike → p95 above 50 → not flagged here (idle_vms picks it up if low p95)
        metric_record(vm_id="/idle-burst", vm_name="idle-burst", avg_pct=5, p95_pct=70, max_pct=90),
    ]
    paths = snapshot_factory({"sub-1": {"vms": vms, "vm_metrics": metrics}})
    ctx = RuleContext.from_snapshot(paths, cost_knowledge)
    flagged = [f for f in oversized_vms.evaluate(ctx) if f.severity == Severity.MEDIUM]
    assert flagged == []


def test_sparse_metrics_silently_skipped_not_info(snapshot_factory, cost_knowledge):
    """oversized_vms is the more permissive rule; we already emit Info from idle_vms,
    so duplicate Info findings would be noise. oversized_vms simply skips sparse VMs."""
    vms = [vm_record(vm_id="/sub/vms/sparse", name="sparse")]
    metrics = [metric_record(vm_id="/sub/vms/sparse", vm_name="sparse", points=10, avg_pct=2)]
    paths = snapshot_factory({"sub-1": {"vms": vms, "vm_metrics": metrics}})
    ctx = RuleContext.from_snapshot(paths, cost_knowledge)
    findings = list(oversized_vms.evaluate(ctx))
    assert findings == []


def test_knowledge_refs_present(cost_knowledge):
    for ref in oversized_vms.KNOWLEDGE_REFS:
        assert cost_knowledge.has(ref)
