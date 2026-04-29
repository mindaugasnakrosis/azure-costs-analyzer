"""unattached_public_ips — Standard SKU IPs with no ipConfiguration.

Authority: `knowledge/public-ip-orphan.md`. Two findings:

1. Any Standard / StandardV2 IPv4 with `ipConfiguration is None` (Medium severity).
2. Any remaining Basic SKU public IPv4 — Microsoft retired Basic SKU on
   2025-09-30 (High severity, deterministic).
"""

from __future__ import annotations

from collections.abc import Iterable
from decimal import Decimal

from azure_investigator_core.schema import Confidence, Finding, Severity

from .base import RuleContext, info_missing_data, savings_range

RULE_ID = "unattached_public_ips"
KNOWLEDGE_REFS = ["public-ip-orphan.md", "azure-advisor-cost-rules.md"]

# Order-of-magnitude GBP/month for an idle Standard SKU IPv4.
_STANDARD_BAND = (Decimal("2.50"), Decimal("3.20"))


def evaluate(ctx: RuleContext) -> Iterable[Finding]:
    findings: list[Finding] = []
    for sub in ctx.subscriptions():
        ips = ctx.data_for(sub.id, "public_ips")
        if ips is None:
            findings.append(
                info_missing_data(
                    rule_id=RULE_ID,
                    title="Unattached public IPs",
                    subscription=sub,
                    missing_collector="public_ips",
                )
            )
            continue
        for ip in ips:
            if ip.get("ipConfiguration") is not None:
                continue
            sku_name = ((ip.get("sku") or {}).get("name")) or "Unknown"
            version = ip.get("publicIPAddressVersion") or "IPv4"
            if version != "IPv4":
                continue
            common = dict(
                rule_id=RULE_ID,
                subscription_id=sub.id,
                subscription_name=sub.name,
                region=ip.get("location"),
                resource_id=ip.get("id"),
                resource_name=ip.get("name"),
                knowledge_refs=KNOWLEDGE_REFS,
            )
            if sku_name == "Basic":
                findings.append(
                    Finding(
                        **common,
                        title=f"Basic SKU public IP (retired tier): {ip.get('name')}",
                        severity=Severity.HIGH,
                        confidence=Confidence.HIGH,
                        evidence={"sku": sku_name, "ipAddress": ip.get("ipAddress")},
                        recommended_investigation=(
                            "Microsoft retired Basic SKU public IPs on 2025-09-30. "
                            "Confirm whether this address is still required and, "
                            "if so, plan an upgrade to Standard SKU; otherwise "
                            "release it."
                        ),
                    )
                )
            elif sku_name in {"Standard", "StandardV2"}:
                findings.append(
                    Finding(
                        **common,
                        title=f"Unattached Standard public IP: {ip.get('name')}",
                        severity=Severity.MEDIUM,
                        confidence=Confidence.HIGH,
                        estimated_savings=savings_range(
                            _STANDARD_BAND[0],
                            _STANDARD_BAND[1],
                            assumption=(
                                "Assumes the IP remains unattached and is not "
                                "required for an outbound-firewall pinhole or "
                                "DNS A record. Band uses retail Standard SKU "
                                "IPv4 rates."
                            ),
                        ),
                        evidence={
                            "sku": sku_name,
                            "ipAddress": ip.get("ipAddress"),
                            "allocationMethod": ip.get("publicIPAllocationMethod"),
                        },
                        recommended_investigation=(
                            "Confirm the address isn't allow-listed by an "
                            "external partner before release; static IPv4 is "
                            "released permanently on delete (Microsoft)."
                        ),
                    )
                )
    return findings
