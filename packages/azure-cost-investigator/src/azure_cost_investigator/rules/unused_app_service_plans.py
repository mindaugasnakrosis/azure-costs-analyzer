"""unused_app_service_plans — Dedicated-tier plans with zero apps.

Authority: `knowledge/app-service-plan-utilisation.md` (Microsoft's verbatim
billing rule that the *plan* — not the apps — is what's charged on dedicated
tiers) and `knowledge/azure-advisor-cost-rules.md` (Advisor "Unused/Empty App
Service plan", recommendation id `39a8510f-5bbf-4304-9bcd-4106c996473b`).

Severity: High — actively burning money on a dedicated VM with no workload.
Confidence: High — deterministic from inventory.
"""

from __future__ import annotations

from collections.abc import Iterable

from azure_investigator_core.schema import Confidence, Finding, Severity

from .base import RuleContext, info_missing_data, savings_range

RULE_ID = "unused_app_service_plans"
KNOWLEDGE_REFS = ["app-service-plan-utilisation.md", "azure-advisor-cost-rules.md"]

# Tiers that bill per-VM-instance regardless of apps. Free + Shared are
# excluded (Free is free; Shared is per-app CPU minutes).
DEDICATED_TIERS = {
    "Basic",
    "Standard",
    "Premium",
    "PremiumV2",
    "PremiumV3",
    "PremiumV4",
    "Premium0V3",  # P0v3 ships under this tier label in some regions
    "Isolated",
    "IsolatedV2",
    "WorkflowStandard",  # Logic Apps Standard plans bill per-instance
}

# Order-of-magnitude GBP/month per *instance* by tier family. Refined at
# report time via PricingClient when available.
_TIER_BANDS = {
    "Basic": (10, 70),
    "Standard": (50, 200),
    "Premium": (100, 350),
    "PremiumV2": (100, 350),
    "PremiumV3": (90, 600),
    "Premium0V3": (35, 70),
    "PremiumV4": (90, 600),
    "Isolated": (200, 800),
    "IsolatedV2": (200, 800),
    "WorkflowStandard": (140, 280),
}


def evaluate(ctx: RuleContext) -> Iterable[Finding]:
    findings: list[Finding] = []
    for sub in ctx.subscriptions():
        plans = ctx.data_for(sub.id, "app_service_plans")
        if plans is None:
            findings.append(
                info_missing_data(
                    rule_id=RULE_ID,
                    title="Unused App Service plans",
                    subscription=sub,
                    missing_collector="app_service_plans",
                )
            )
            continue
        for p in plans:
            tier = ((p.get("sku") or {}).get("tier")) or ""
            if tier not in DEDICATED_TIERS:
                continue
            apps = int(p.get("numberOfSites") or 0)
            if apps > 0:
                continue
            workers = int(p.get("numberOfWorkers") or 1)
            sku_size = ((p.get("sku") or {}).get("name")) or "?"
            band = _TIER_BANDS.get(tier, (50, 200))
            findings.append(
                Finding(
                    rule_id=RULE_ID,
                    title=f"Empty App Service plan ({tier} {sku_size}): {p.get('name')}",
                    subscription_id=sub.id,
                    subscription_name=sub.name,
                    region=p.get("location"),
                    resource_id=p.get("id"),
                    resource_name=p.get("name"),
                    severity=Severity.HIGH,
                    confidence=Confidence.HIGH,
                    estimated_savings=savings_range(
                        band[0] * workers,
                        band[1] * workers,
                        assumption=(
                            f"Microsoft: 'each VM instance in the App Service "
                            f"plan is charged… regardless of how many apps "
                            f"are running on them.' Band assumes {workers} "
                            f"worker(s) at retail {tier} {sku_size} rates."
                        ),
                    ),
                    knowledge_refs=KNOWLEDGE_REFS,
                    evidence={
                        "tier": tier,
                        "sku_size": sku_size,
                        "numberOfSites": apps,
                        "numberOfWorkers": workers,
                        "tags": p.get("tags") or {},
                    },
                    recommended_investigation=(
                        "Confirm no upcoming deployment is parked against "
                        "this plan. If genuinely unused, the plan can be "
                        "deleted via the Azure Portal or `az appservice "
                        "plan delete` — out of scope for this skill, which "
                        "is read-only."
                    ),
                )
            )
    return findings
