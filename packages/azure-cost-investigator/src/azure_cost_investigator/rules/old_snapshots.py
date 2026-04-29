"""old_snapshots — disk snapshots older than the configured retention threshold.

Authority: `knowledge/azure-advisor-cost-rules.md` (Advisor "Use Standard
Storage to store Managed Disks snapshots", id `702b474d-…`) and
`knowledge/storage-tiering.md` (90-day Cool tier minimum).

The rule defaults to flagging snapshots older than 90 days, the Cool-tier
minimum-retention threshold — past that age, the cost case for keeping the
snapshot live becomes the user's to defend. Severity Medium, Confidence High.
"""

from __future__ import annotations

from collections.abc import Iterable
from datetime import UTC, datetime

from azure_investigator_core.schema import Confidence, Finding, Severity

from .base import RuleContext, info_missing_data, savings_range

RULE_ID = "old_snapshots"
KNOWLEDGE_REFS = ["azure-advisor-cost-rules.md", "storage-tiering.md"]

DEFAULT_AGE_DAYS = 90

# GBP/GB-month bands for Standard / Premium snapshot storage.
_BANDS = {
    "Standard_LRS": (0.025, 0.045),
    "Standard_ZRS": (0.030, 0.055),
    "Premium_LRS": (0.10, 0.13),
    "Premium_ZRS": (0.11, 0.14),
}


def evaluate(ctx: RuleContext) -> Iterable[Finding]:
    findings: list[Finding] = []
    age_days = int(ctx.config.get("snapshot_age_days", DEFAULT_AGE_DAYS))
    cutoff = datetime.now(UTC).timestamp() - age_days * 86400

    for sub in ctx.subscriptions():
        snaps = ctx.data_for(sub.id, "snapshots")
        if snaps is None:
            findings.append(
                info_missing_data(
                    rule_id=RULE_ID,
                    title="Old disk snapshots",
                    subscription=sub,
                    missing_collector="snapshots",
                )
            )
            continue
        for s in snaps:
            created = s.get("timeCreated")
            if not created:
                continue
            try:
                ts = datetime.fromisoformat(created.replace("Z", "+00:00")).timestamp()
            except (ValueError, AttributeError):
                continue
            if ts > cutoff:
                continue
            age = int((datetime.now(UTC).timestamp() - ts) / 86400)
            sku_name = ((s.get("sku") or {}).get("name")) or "Standard_LRS"
            size_gb = int(s.get("diskSizeGB") or s.get("diskSizeGb") or 0)
            band = _BANDS.get(sku_name, (0.03, 0.05))
            low = band[0] * size_gb
            high = band[1] * size_gb
            findings.append(
                Finding(
                    rule_id=RULE_ID,
                    title=f"Old snapshot ({age}d, {sku_name} {size_gb} GB): {s.get('name')}",
                    subscription_id=sub.id,
                    subscription_name=sub.name,
                    region=s.get("location"),
                    resource_id=s.get("id"),
                    resource_name=s.get("name"),
                    severity=Severity.MEDIUM,
                    confidence=Confidence.HIGH,
                    estimated_savings=savings_range(
                        low,
                        high,
                        assumption=(
                            f"Assumes the snapshot is no longer required for "
                            f"recovery. Band uses {sku_name} retail rates × "
                            f"{size_gb} GB; if the snapshot is on Premium and "
                            f"can move to Standard, Microsoft's published "
                            f"'60% reduction' (Advisor) applies first."
                        ),
                    ),
                    knowledge_refs=KNOWLEDGE_REFS,
                    evidence={
                        "age_days": age,
                        "size_gb": size_gb,
                        "sku": sku_name,
                        "time_created": created,
                        "source_disk_id": s.get("creationData", {}).get("sourceResourceId"),
                    },
                    recommended_investigation=(
                        "Confirm the snapshot's source disk still exists and "
                        "the snapshot is retained for a stated recovery "
                        "objective. If on Premium storage, evaluate moving "
                        "to Standard before deletion."
                    ),
                )
            )
    return findings
