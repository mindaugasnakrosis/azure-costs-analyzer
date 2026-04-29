"""idle_vms — VMs with sustained low CPU over a 14-day window.

Authority: `knowledge/vm-rightsizing-thresholds.md` (Advisor's published
shutdown criteria). Microsoft's verbatim trigger is:

> A shutdown recommendation is created if:
>   - P95 of the maximum value of CPU utilization summed across all cores is less than 3%
>   - P100 of average CPU in last 3 days (sum over all cores) <= 2%
>   - Outbound Network utilization is less than 2% over a seven-day period

We don't yet collect per-VM outbound network metrics, so confidence is
**Medium** rather than High and the rule states the missing-data caveat in
`recommended_investigation`. The CPU thresholds are taken verbatim.
"""

from __future__ import annotations

from collections.abc import Iterable

from azure_investigator_core.schema import Confidence, Finding, Severity

from .base import RuleContext, info_missing_data, savings_range
from .stopped_not_deallocated_vms import _band_high, _band_low

RULE_ID = "idle_vms"
KNOWLEDGE_REFS = ["vm-rightsizing-thresholds.md", "azure-advisor-cost-rules.md"]

# Defaults sourced verbatim from the Advisor doc.
P95_CPU_PCT_LIMIT = 3.0
MIN_DATAPOINTS = 168  # 7 days × 24 hourly samples — refuse to evaluate sparser series


def evaluate(ctx: RuleContext) -> Iterable[Finding]:
    findings: list[Finding] = []
    threshold = float(ctx.config.get("idle_p95_pct", P95_CPU_PCT_LIMIT))
    min_pts = int(ctx.config.get("idle_min_datapoints", MIN_DATAPOINTS))

    for sub in ctx.subscriptions():
        vms = ctx.data_for(sub.id, "vms")
        metrics = ctx.data_for(sub.id, "vm_metrics")
        if vms is None or metrics is None:
            findings.append(
                info_missing_data(
                    rule_id=RULE_ID,
                    title="Idle VMs",
                    subscription=sub,
                    missing_collector="vms" if vms is None else "vm_metrics",
                )
            )
            continue
        vm_by_id = {vm.get("id"): vm for vm in vms}
        for rec in metrics:
            stats = _cpu_stats(rec)
            vm = vm_by_id.get(rec.get("vm_id"))
            if vm is None:
                continue
            if stats["count"] < min_pts:
                findings.append(
                    Finding(
                        rule_id=RULE_ID,
                        title=f"Idle VM check: insufficient metrics for {rec.get('vm_name')}",
                        subscription_id=sub.id,
                        subscription_name=sub.name,
                        region=rec.get("region"),
                        resource_id=rec.get("vm_id"),
                        resource_name=rec.get("vm_name"),
                        severity=Severity.INFO,
                        confidence=Confidence.HIGH,
                        knowledge_refs=[],
                        evidence={
                            "datapoints": stats["count"],
                            "min_required": min_pts,
                            "window_days": 14,
                        },
                        recommended_investigation=(
                            "VM metrics window is too sparse to evaluate "
                            "(possibly an ephemeral compute resource). "
                            "Re-run after the VM has been running 7+ days."
                        ),
                    )
                )
                continue
            if stats["p95"] < threshold:
                sku = (vm.get("hardwareProfile") or {}).get("vmSize", "Unknown")
                findings.append(
                    Finding(
                        rule_id=RULE_ID,
                        title=f"Idle VM (P95 CPU {stats['p95']:.1f}% over 14d): {vm.get('name')}",
                        subscription_id=sub.id,
                        subscription_name=sub.name,
                        region=vm.get("location"),
                        resource_id=vm.get("id"),
                        resource_name=vm.get("name"),
                        severity=Severity.MEDIUM,
                        confidence=Confidence.MEDIUM,
                        estimated_savings=savings_range(
                            _band_low(sku),
                            _band_high(sku),
                            assumption=(
                                f"Assumes the workload can be paused or "
                                f"deallocated. Band uses retail compute rates "
                                f"for {sku}; outbound-network metric not yet "
                                f"collected so we cannot confirm Microsoft's "
                                f"full Advisor shutdown criterion."
                            ),
                        ),
                        knowledge_refs=KNOWLEDGE_REFS,
                        evidence={
                            "p95_cpu_pct": round(stats["p95"], 2),
                            "avg_cpu_pct": round(stats["avg"], 2),
                            "max_cpu_pct": round(stats["max"], 2),
                            "datapoints": stats["count"],
                            "window_days": 14,
                            "vmSize": sku,
                            "tags": vm.get("tags") or {},
                        },
                        recommended_investigation=(
                            "Confirm with the workload owner that the low CPU "
                            "is not by-design batch behaviour. Microsoft's "
                            "Advisor caveat applies: savings figures are "
                            "retail-rate ceilings and don't net out reservations."
                        ),
                    )
                )
    return findings


def _cpu_stats(rec: dict) -> dict:
    metrics = rec.get("metrics") or {}
    values: list[float] = []
    for m in metrics.get("value", []):
        for ts in m.get("timeseries", []):
            for d in ts.get("data", []):
                avg = d.get("average")
                if avg is not None:
                    values.append(float(avg))
    if not values:
        return {"count": 0, "avg": 0.0, "p95": 0.0, "max": 0.0}
    values.sort()
    n = len(values)
    # Nearest-rank P95: lowest value v such that ≥95% of samples are ≤ v.
    p95_idx = min(n - 1, max(0, int(n * 0.95)))
    return {
        "count": n,
        "avg": sum(values) / n,
        "p95": values[p95_idx],
        "max": values[-1],
    }
