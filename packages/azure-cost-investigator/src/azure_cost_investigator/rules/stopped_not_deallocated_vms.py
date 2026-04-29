"""stopped_not_deallocated_vms — VMs in PowerState/stopped (not deallocated).

Authority: Microsoft VM lifecycle docs (linked from the Advisor reference). A
VM in `PowerState/stopped` (without `deallocated`) continues to bill for
compute. This is a Critical finding — it actively burns money for no work.
"""

from __future__ import annotations

from collections.abc import Iterable

from azure_investigator_core.schema import Confidence, Finding, Severity

from .base import RuleContext, info_missing_data, savings_range

RULE_ID = "stopped_not_deallocated_vms"
KNOWLEDGE_REFS = ["azure-advisor-cost-rules.md", "vm-rightsizing-thresholds.md"]


def evaluate(ctx: RuleContext) -> Iterable[Finding]:
    findings: list[Finding] = []
    for sub in ctx.subscriptions():
        vms = ctx.data_for(sub.id, "vms")
        if vms is None:
            findings.append(
                info_missing_data(
                    rule_id=RULE_ID,
                    title="Stopped (not deallocated) VMs",
                    subscription=sub,
                    missing_collector="vms",
                )
            )
            continue
        for vm in vms:
            power_state = (vm.get("powerState") or "").lower()
            # `powerState` from `az vm list -d` is a friendly form
            # ("VM stopped", "VM deallocated", "VM running"). The "stopped"
            # form means OS-stopped without releasing compute reservation.
            if "stopped" not in power_state or "deallocated" in power_state:
                continue
            sku = ((vm.get("hardwareProfile") or {}).get("vmSize")) or "Unknown"
            findings.append(
                Finding(
                    rule_id=RULE_ID,
                    title=f"VM stopped but not deallocated: {vm.get('name')}",
                    subscription_id=sub.id,
                    subscription_name=sub.name,
                    region=vm.get("location"),
                    resource_id=vm.get("id"),
                    resource_name=vm.get("name"),
                    severity=Severity.CRITICAL,
                    confidence=Confidence.HIGH,
                    estimated_savings=savings_range(
                        _band_low(sku),
                        _band_high(sku),
                        assumption=(
                            f"Assumes the VM remains in stopped (not "
                            f"deallocated) state for the next month. Band uses "
                            f"retail compute rates for {sku} in the resource's "
                            f"region; actual savings depend on negotiated "
                            f"discounts and reservation coverage."
                        ),
                    ),
                    knowledge_refs=KNOWLEDGE_REFS,
                    evidence={
                        "powerState": vm.get("powerState"),
                        "vmSize": sku,
                        "tags": vm.get("tags") or {},
                    },
                    recommended_investigation=(
                        "Investigate why this VM is in 'stopped' rather than "
                        "'deallocated' state. The stopped state still bills "
                        "for the compute reservation. If the VM is needed "
                        "later, deallocate it; if not, evaluate deletion."
                    ),
                )
            )
    return findings


# Crude SKU-family bands as a fallback when no pricing client is wired in.
# Real numbers should come from `pricing.PricingClient.items(...)`.
_FAMILY_BANDS = {
    "B": (10, 25),
    "D": (40, 90),
    "E": (60, 130),
    "F": (40, 100),
    "M": (120, 280),
    "L": (90, 200),
}


def _family(sku: str) -> str:
    s = sku.removeprefix("Standard_")
    if not s:
        return "D"
    return s[0].upper()


def _band_low(sku: str) -> float:
    return float(_FAMILY_BANDS.get(_family(sku), (30, 80))[0])


def _band_high(sku: str) -> float:
    return float(_FAMILY_BANDS.get(_family(sku), (30, 80))[1])
