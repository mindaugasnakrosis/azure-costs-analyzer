"""legacy_storage_redundancy — Hot-tier storage accounts running a higher
redundancy SKU than the access pattern needs.

Authority: `knowledge/storage-tiering.md` (Hot-tier definition + the rule
that LRS/GRS/RA-GRS support archive while ZRS-family accounts do not — i.e.
LRS/GRS/RA-GRS are the "legacy" redundancy SKUs that often sit on
production-grade dev workloads).

We restrict v1 to a deterministic signal: GRS/RA-GRS accounts whose access
tier is Hot — the geo-replicated copy bills GBP/GB-month and is wasted if
the data is dev/test. ZRS-family accounts are intentionally excluded because
they are zone-redundant by design and not "legacy".

Severity: Low (architectural). Confidence: Medium (replication choice is
business-driven; we can't see the customer's RPO/RTO requirement).
"""

from __future__ import annotations

from collections.abc import Iterable

from azure_investigator_core.schema import Confidence, Finding, Severity

from .base import RuleContext, info_missing_data

RULE_ID = "legacy_storage_redundancy"
KNOWLEDGE_REFS = ["storage-tiering.md", "azure-well-architected-cost.md"]

# SKUs we consider candidates (geo-replicated, paying ~2× the LRS rate).
GEO_REPL_SKUS = {"Standard_GRS", "Standard_RAGRS", "Standard_GZRS", "Standard_RAGZRS"}

# Tag values we treat as "non-prod" — geo-redundancy on non-prod storage is
# the strongest signal of misconfiguration.
NONPROD_VALUES = {"dev", "test", "qa", "uat", "staging", "stg", "sandbox", "ppe"}


def _env(tags: dict | None) -> str | None:
    if not tags:
        return None
    for k in ("env", "environment", "Env", "Environment", "ENV", "ENVIRONMENT"):
        if k in tags and tags[k]:
            return str(tags[k]).strip().lower()
    return None


def evaluate(ctx: RuleContext) -> Iterable[Finding]:
    findings: list[Finding] = []
    for sub in ctx.subscriptions():
        accounts = ctx.data_for(sub.id, "storage_accounts")
        if accounts is None:
            findings.append(
                info_missing_data(
                    rule_id=RULE_ID,
                    title="Geo-redundant storage on non-prod accounts",
                    subscription=sub,
                    missing_collector="storage_accounts",
                )
            )
            continue
        for acc in accounts:
            sku_name = ((acc.get("sku") or {}).get("name")) or ""
            if sku_name not in GEO_REPL_SKUS:
                continue
            access_tier = acc.get("accessTier") or "Hot"
            env = _env(acc.get("tags"))
            severity = Severity.LOW
            if env in NONPROD_VALUES:
                severity = Severity.MEDIUM  # stronger when the env tag confirms non-prod
            findings.append(
                Finding(
                    rule_id=RULE_ID,
                    title=(f"Geo-redundant storage ({sku_name}, {access_tier}): {acc.get('name')}"),
                    subscription_id=sub.id,
                    subscription_name=sub.name,
                    region=acc.get("location"),
                    resource_id=acc.get("id"),
                    resource_name=acc.get("name"),
                    severity=severity,
                    confidence=Confidence.MEDIUM,
                    knowledge_refs=KNOWLEDGE_REFS,
                    evidence={
                        "sku": sku_name,
                        "access_tier": access_tier,
                        "env_tag": env,
                        "tags": acc.get("tags") or {},
                    },
                    recommended_investigation=(
                        "Geo-replicated accounts roughly double per-GB "
                        "storage cost vs LRS. Confirm the RPO requirement "
                        "justifies cross-region replication; non-prod data "
                        "rarely does. Consider LRS or ZRS where appropriate."
                    ),
                )
            )
    return findings
