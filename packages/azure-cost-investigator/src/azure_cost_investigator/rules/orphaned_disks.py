"""orphaned_disks — managed disks with no parent VM.

Authority: see `knowledge/disk-orphan-criteria.md` and the Advisor entry in
`knowledge/azure-advisor-cost-rules.md`. Confidence is High because the signal
is deterministic from inventory; no metrics window is involved.
"""

from __future__ import annotations

from collections.abc import Iterable
from decimal import Decimal

from azure_investigator_core.schema import Confidence, Finding, Severity

from .base import RuleContext, info_missing_data, savings_range

RULE_ID = "orphaned_disks"
KNOWLEDGE_REFS = ["disk-orphan-criteria.md", "azure-advisor-cost-rules.md"]

# Microsoft documents two states for a disk that survived its VM. Both,
# combined with managedBy=null, are unambiguously orphans.
ORPHAN_STATES = {"Unattached", "Reserved"}


def evaluate(ctx: RuleContext) -> Iterable[Finding]:
    findings: list[Finding] = []
    for sub in ctx.subscriptions():
        disks = ctx.data_for(sub.id, "disks")
        if disks is None:
            findings.append(
                info_missing_data(
                    rule_id=RULE_ID,
                    title="Orphaned managed disks",
                    subscription=sub,
                    missing_collector="disks",
                )
            )
            continue
        for d in disks:
            if d.get("managedBy"):
                continue
            state = d.get("diskState")
            if state not in ORPHAN_STATES:
                continue
            size_gb = int(d.get("diskSizeGB") or d.get("diskSizeGb") or 0)
            sku_name = ((d.get("sku") or {}).get("name")) or "Unknown"
            tier = ((d.get("sku") or {}).get("tier")) or "Unknown"
            low, high = _estimate_monthly_gbp(size_gb=size_gb, sku=sku_name)
            findings.append(
                Finding(
                    rule_id=RULE_ID,
                    title=f"Orphaned managed disk: {d.get('name')}",
                    subscription_id=sub.id,
                    subscription_name=sub.name,
                    region=d.get("location"),
                    resource_id=d.get("id"),
                    resource_name=d.get("name"),
                    severity=Severity.MEDIUM,
                    confidence=Confidence.HIGH,
                    estimated_savings=savings_range(
                        low,
                        high,
                        assumption=(
                            f"Assumes the disk is genuinely orphaned and not a "
                            f"manual backup. Cost band uses retail rates for "
                            f"{tier} {sku_name} {size_gb} GB; actual savings "
                            f"depend on negotiated discounts and reservations."
                        ),
                    ),
                    knowledge_refs=KNOWLEDGE_REFS,
                    evidence={
                        "diskState": state,
                        "managedBy": d.get("managedBy"),
                        "sku": sku_name,
                        "tier": tier,
                        "size_gb": size_gb,
                        "time_created": d.get("timeCreated"),
                    },
                    recommended_investigation=(
                        "Per Microsoft: 'Deletions are permanent, you will not be "
                        "able to recover data once you delete a disk.' Confirm "
                        "the disk is not a manual backup; create a snapshot "
                        "before any deletion decision."
                    ),
                )
            )
    return findings


# Conservative GBP/month bands by tier + size. Source: order-of-magnitude
# from Microsoft's published [managed disks pricing page]; the analyser
# refines per-disk savings via the Retail Prices API at report time when a
# pricing client is wired up.
_TIER_BAND_GBP_PER_GB_MONTH = {
    "Premium_LRS": (Decimal("0.12"), Decimal("0.15")),
    "Premium_ZRS": (Decimal("0.13"), Decimal("0.17")),
    "PremiumV2_LRS": (Decimal("0.10"), Decimal("0.14")),
    "StandardSSD_LRS": (Decimal("0.06"), Decimal("0.09")),
    "StandardSSD_ZRS": (Decimal("0.07"), Decimal("0.10")),
    "Standard_LRS": (Decimal("0.03"), Decimal("0.05")),
    "UltraSSD_LRS": (Decimal("0.18"), Decimal("0.30")),
}


def _estimate_monthly_gbp(*, size_gb: int, sku: str) -> tuple[Decimal, Decimal]:
    if size_gb <= 0:
        return Decimal("0"), Decimal("0")
    low, high = _TIER_BAND_GBP_PER_GB_MONTH.get(sku, (Decimal("0.04"), Decimal("0.10")))
    return (low * size_gb, high * size_gb)
