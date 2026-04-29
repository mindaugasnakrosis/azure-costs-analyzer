"""dev_skus_in_prod — VMs / App Service plans tagged for production but
running on dev-tier SKUs (or vice versa: high-grade SKUs in TEST/dev tags).

Authority: WAF Cost Optimization, Principle 2 — *"Treat different SDLC
environments differently. […] Nonproduction environments can have different
features, SKUs, instance counts, and even logging."* And the CAF tagging
schema (`knowledge/tagging-and-governance.md`) for the canonical `env` /
`environment` tag values.

Severity: Medium (architectural mismatch, not active waste).
Confidence: Medium (tag conventions vary by tenant; we read the conservative
CAF set).
"""

from __future__ import annotations

from collections.abc import Iterable

from azure_investigator_core.schema import Confidence, Finding, Severity

from .base import RuleContext, info_missing_data

RULE_ID = "dev_skus_in_prod"
KNOWLEDGE_REFS = ["azure-well-architected-cost.md", "tagging-and-governance.md"]

# Tag keys we accept as the environment classifier (lowercase comparison).
ENV_TAG_KEYS = ("env", "environment", "Env", "Environment", "ENV", "ENVIRONMENT")
PROD_VALUES = {"prod", "production", "live"}
NONPROD_VALUES = {"dev", "test", "qa", "uat", "staging", "stg", "sandbox", "ppe"}

# VM SKUs we class as dev-grade (low-cost, B-series and small DS).
DEV_VM_SKUS = {
    "Standard_B1s",
    "Standard_B1ms",
    "Standard_B2s",
    "Standard_B2ms",
    "Standard_B4ms",
    "Standard_A1_v2",
    "Standard_A2_v2",
    "Standard_DS1_v2",
    "Standard_D1_v2",
}

# App Service plan tiers we class as production-grade.
PROD_ASP_TIERS = {"PremiumV3", "PremiumV4", "Premium", "PremiumV2", "IsolatedV2"}
DEV_ASP_TIERS = {"Free", "Shared", "Basic"}


def _env(tags: dict | None) -> str | None:
    if not tags:
        return None
    for key in ENV_TAG_KEYS:
        if key in tags and tags[key]:
            return str(tags[key]).strip().lower()
    return None


def evaluate(ctx: RuleContext) -> Iterable[Finding]:
    findings: list[Finding] = []
    for sub in ctx.subscriptions():
        vms = ctx.data_for(sub.id, "vms")
        plans = ctx.data_for(sub.id, "app_service_plans")
        if vms is None and plans is None:
            findings.append(
                info_missing_data(
                    rule_id=RULE_ID,
                    title="Dev SKUs in prod / prod SKUs in dev",
                    subscription=sub,
                    missing_collector="vms+app_service_plans",
                )
            )
            continue

        for vm in vms or []:
            env = _env(vm.get("tags"))
            sku = (vm.get("hardwareProfile") or {}).get("vmSize", "")
            if env in PROD_VALUES and sku in DEV_VM_SKUS:
                findings.append(
                    _vm_finding(
                        sub=sub,
                        vm=vm,
                        sku=sku,
                        env=env,
                        direction="dev SKU on prod-tagged VM",
                        note=(
                            "Dev-grade VM SKU running under a production tag — "
                            "either the tag is wrong or the workload deserves "
                            "a real production SKU."
                        ),
                    )
                )
            elif env in NONPROD_VALUES and sku.startswith(
                ("Standard_M", "Standard_E64", "Standard_E32")
            ):
                findings.append(
                    _vm_finding(
                        sub=sub,
                        vm=vm,
                        sku=sku,
                        env=env,
                        direction="prod-grade SKU on non-prod-tagged VM",
                        note=(
                            "High-end VM SKU running under a non-production "
                            "tag. WAF: 'nonproduction environments can have "
                            "different features, SKUs, instance counts.'"
                        ),
                    )
                )

        for p in plans or []:
            env = _env(p.get("tags"))
            tier = ((p.get("sku") or {}).get("tier")) or ""
            if env in PROD_VALUES and tier in DEV_ASP_TIERS:
                findings.append(
                    _asp_finding(
                        sub=sub,
                        plan=p,
                        tier=tier,
                        env=env,
                        direction="dev tier on prod-tagged App Service Plan",
                        note=(
                            "Dev-tier App Service plan under a production tag. "
                            "Free/Shared/Basic tiers are documented for "
                            "development and testing only."
                        ),
                    )
                )
            elif env in NONPROD_VALUES and tier in PROD_ASP_TIERS:
                findings.append(
                    _asp_finding(
                        sub=sub,
                        plan=p,
                        tier=tier,
                        env=env,
                        direction="prod tier on non-prod-tagged App Service Plan",
                        note=(
                            "Premium-tier plan under a non-production tag. "
                            "WAF Principle 2: SDLC environments should be "
                            "right-sized differently."
                        ),
                    )
                )
    return findings


def _vm_finding(*, sub, vm, sku: str, env: str, direction: str, note: str) -> Finding:
    return Finding(
        rule_id=RULE_ID,
        title=f"Environment / SKU mismatch ({direction}): {vm.get('name')}",
        subscription_id=sub.id,
        subscription_name=sub.name,
        region=vm.get("location"),
        resource_id=vm.get("id"),
        resource_name=vm.get("name"),
        severity=Severity.MEDIUM,
        confidence=Confidence.MEDIUM,
        knowledge_refs=KNOWLEDGE_REFS,
        evidence={
            "env_tag": env,
            "vmSize": sku,
            "tags": vm.get("tags") or {},
        },
        recommended_investigation=(
            f"{note} Confirm the environment tag is accurate and decide whether to retag or resize."
        ),
    )


def _asp_finding(*, sub, plan, tier: str, env: str, direction: str, note: str) -> Finding:
    return Finding(
        rule_id=RULE_ID,
        title=f"Environment / tier mismatch ({direction}): {plan.get('name')}",
        subscription_id=sub.id,
        subscription_name=sub.name,
        region=plan.get("location"),
        resource_id=plan.get("id"),
        resource_name=plan.get("name"),
        severity=Severity.MEDIUM,
        confidence=Confidence.MEDIUM,
        knowledge_refs=KNOWLEDGE_REFS,
        evidence={
            "env_tag": env,
            "tier": tier,
            "sku_size": ((plan.get("sku") or {}).get("name")),
            "tags": plan.get("tags") or {},
        },
        recommended_investigation=(
            f"{note} Confirm the environment tag is accurate and decide "
            f"whether to retag or rescale the plan."
        ),
    )
