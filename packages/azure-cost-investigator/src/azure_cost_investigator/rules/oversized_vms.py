"""oversized_vms — VMs that are running but consistently below their SKU's headroom.

Authority: `knowledge/vm-rightsizing-thresholds.md`. Microsoft's verbatim
target for a *user-facing* workload on a recommended (smaller) SKU is:

> P95 of CPU and Outbound Network utilization at 40% or lower on the recommended SKU
> P99 of Memory utilization at 60% or lower on the recommended SKU

We approximate by flagging current SKUs where 14-day **avg < 25% AND P95 < 50%**
— if a smaller SKU exists in the same family, the workload would still meet
Microsoft's user-facing target on that SKU. We don't recommend a specific SKU
in v1; the user investigates via Advisor or `az vm list-skus`.

Confidence: **Low** — workload classification (user-facing vs non) and memory
data are not available in our snapshot.
"""

from __future__ import annotations

from collections.abc import Iterable

from azure_investigator_core.schema import Confidence, Finding, Severity

from .base import RuleContext, info_missing_data, savings_range
from .idle_vms import _cpu_stats
from .stopped_not_deallocated_vms import _band_high, _band_low

RULE_ID = "oversized_vms"
KNOWLEDGE_REFS = [
    "vm-rightsizing-thresholds.md",
    "azure-advisor-cost-rules.md",
    "pricing-sources.md",
]

AVG_CPU_PCT_LIMIT = 25.0
P95_CPU_PCT_LIMIT = 50.0
MIN_DATAPOINTS = 168


def evaluate(ctx: RuleContext) -> Iterable[Finding]:
    findings: list[Finding] = []
    avg_limit = float(ctx.config.get("oversized_avg_pct", AVG_CPU_PCT_LIMIT))
    p95_limit = float(ctx.config.get("oversized_p95_pct", P95_CPU_PCT_LIMIT))
    min_pts = int(ctx.config.get("oversized_min_datapoints", MIN_DATAPOINTS))

    for sub in ctx.subscriptions():
        vms = ctx.data_for(sub.id, "vms")
        metrics = ctx.data_for(sub.id, "vm_metrics")
        if vms is None or metrics is None:
            findings.append(
                info_missing_data(
                    rule_id=RULE_ID,
                    title="Oversized VMs",
                    subscription=sub,
                    missing_collector="vms" if vms is None else "vm_metrics",
                )
            )
            continue
        vm_by_id = {vm.get("id"): vm for vm in vms}
        for rec in metrics:
            stats = _cpu_stats(rec)
            vm = vm_by_id.get(rec.get("vm_id"))
            if vm is None or stats["count"] < min_pts:
                continue
            if stats["avg"] >= avg_limit or stats["p95"] >= p95_limit:
                continue
            sku = (vm.get("hardwareProfile") or {}).get("vmSize", "Unknown")
            # Savings band: assume the workload moves to roughly half the
            # current SKU's hourly rate (Advisor's typical resize is one step
            # smaller in the same family). Use 30–60% of current monthly band.
            current_low = _band_low(sku)
            current_high = _band_high(sku)
            findings.append(
                Finding(
                    rule_id=RULE_ID,
                    title=(
                        f"Oversized VM (avg {stats['avg']:.1f}%, p95 "
                        f"{stats['p95']:.1f}% over 14d): {vm.get('name')}"
                    ),
                    subscription_id=sub.id,
                    subscription_name=sub.name,
                    region=vm.get("location"),
                    resource_id=vm.get("id"),
                    resource_name=vm.get("name"),
                    severity=Severity.MEDIUM,
                    confidence=Confidence.LOW,
                    estimated_savings=savings_range(
                        current_low * 0.30,
                        current_high * 0.60,
                        assumption=(
                            f"Assumes a one-step-smaller SKU within the same "
                            f"family ({sku}) keeps P95 CPU ≤ 40%. Memory and "
                            f"outbound-network utilisation are not in this "
                            f"snapshot, so the saving is bounded above; "
                            f"validate against Advisor's specific SKU "
                            f"recommendation before planning a change."
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
                        "Cross-reference Advisor's `Right-size or shutdown "
                        "underutilized virtual machines` recommendation for "
                        "the specific target SKU. Confirm memory headroom "
                        "before resizing — this rule only sees CPU."
                    ),
                )
            )
    return findings
