"""untagged_costly_resources — costly resources missing a CAF Accounting or
Functional tag, so cost cannot be allocated.

Authority: `knowledge/tagging-and-governance.md` — Microsoft's Cloud Adoption
Framework names Accounting tags (`costcenter`, `department`, `businessunit`,
`program`) and Functional tags (`env`/`environment`, `app`, `tier`) as the
two foundational categories. Without them, FinOps cost-allocation reports
attribute spend to "Untagged".

We avoid leaning on `consumption.json` for cost (the collector is heavy and
flaky on large subs); instead we restrict the rule to resource types that are
*always* costly when present: VMs, App Service plans, SQL servers/dbs, and
storage accounts. That keeps the noise floor low without a price lookup.

Severity: Low (governance gap, not active waste). Confidence: High.
"""

from __future__ import annotations

from collections.abc import Iterable

from azure_investigator_core.schema import Confidence, Finding, Severity

from .base import RuleContext, info_missing_data

RULE_ID = "untagged_costly_resources"
KNOWLEDGE_REFS = ["tagging-and-governance.md", "finops-framework.md"]

ACCOUNTING_KEYS = {
    "costcenter",
    "cost_center",
    "cost-center",
    "department",
    "businessunit",
    "business_unit",
    "business-unit",
    "program",
    "project",
    "budget",
}
FUNCTIONAL_ENV_KEYS = {"env", "environment"}


def _has_tag(tags: dict | None, accepted: set[str]) -> bool:
    if not tags:
        return False
    keys_lower = {k.lower(): k for k in tags}
    return any(want in keys_lower and tags[keys_lower[want]] for want in accepted)


def _missing_categories(tags: dict | None) -> list[str]:
    missing: list[str] = []
    if not _has_tag(tags, ACCOUNTING_KEYS):
        missing.append("accounting")
    if not _has_tag(tags, FUNCTIONAL_ENV_KEYS):
        missing.append("functional/env")
    return missing


def _emit(*, rule_kind: str, sub, resource: dict, missing: list[str]) -> Finding:
    return Finding(
        rule_id=RULE_ID,
        title=f"Untagged {rule_kind}: {resource.get('name')} missing {', '.join(missing)} tag(s)",
        subscription_id=sub.id,
        subscription_name=sub.name,
        region=resource.get("location"),
        resource_id=resource.get("id"),
        resource_name=resource.get("name"),
        severity=Severity.LOW,
        confidence=Confidence.HIGH,
        knowledge_refs=KNOWLEDGE_REFS,
        evidence={
            "resource_kind": rule_kind,
            "missing_tag_categories": missing,
            "tags": resource.get("tags") or {},
        },
        recommended_investigation=(
            "CAF: 'Centralized IT policies typically enforce core tags.' "
            "Confirm the tagging policy is enforced via Azure Policy and "
            "that this resource is in scope; remediation is out of scope "
            "for this read-only skill."
        ),
    )


def evaluate(ctx: RuleContext) -> Iterable[Finding]:
    findings: list[Finding] = []
    for sub in ctx.subscriptions():
        any_data = False
        for kind, collector in (
            ("VM", "vms"),
            ("App Service plan", "app_service_plans"),
            ("Storage account", "storage_accounts"),
        ):
            data = ctx.data_for(sub.id, collector)
            if data is None:
                continue
            any_data = True
            for r in data:
                missing = _missing_categories(r.get("tags"))
                if missing:
                    findings.append(_emit(rule_kind=kind, sub=sub, resource=r, missing=missing))

        sql = ctx.data_for(sub.id, "sql")
        if sql is not None:
            any_data = True
            for srv in sql.get("servers") or []:
                missing = _missing_categories(srv.get("tags"))
                if missing:
                    findings.append(
                        _emit(rule_kind="SQL server", sub=sub, resource=srv, missing=missing)
                    )

        if not any_data:
            findings.append(
                info_missing_data(
                    rule_id=RULE_ID,
                    title="Untagged costly resources",
                    subscription=sub,
                    missing_collector="vms/app_service_plans/storage_accounts/sql",
                )
            )
    return findings
