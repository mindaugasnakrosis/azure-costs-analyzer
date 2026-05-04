"""rsv_backup_retention — flag Recovery Services Vault retention bloat
and GeoRedundant storage on non-production data.

Authority: `recovery-services-vaults.md`. The rule emits one Finding per
flagged condition per vault. Two flag families:

- **retention_bloat** — any backup policy on the vault retains
  monthly > 12 OR yearly > 5 recovery points. Microsoft's portal default
  ("EnhancedPolicy") is 60 monthly + 10 yearly, far exceeding typical
  audit-compliance contract minima (SOC 2 / ISO 27001 / HIPAA usually
  cap at ≤7 years total).
- **grs_on_nonprod** — the vault is GeoRedundant but the subscription
  name matches a non-prod pattern (test/dev/uat/sandbox/sbox/qa).
  Switching to LocallyRedundant halves the storage line.

Savings band uses the consumption snapshot's `Backup` MeterCategory line
matched on the vault's resource ID. Without consumption data the finding
still surfaces (governance value) but with no band.
"""

from __future__ import annotations

import re
from collections.abc import Iterable
from decimal import Decimal

from azure_investigator_core.schema import Confidence, Finding, Severity

from .base import RuleContext, info_missing_data, savings_range

RULE_ID = "rsv_backup_retention"
KNOWLEDGE_REFS = ["recovery-services-vaults.md", "pricing-sources.md"]

DEFAULT_MONTHLY_LIMIT = 12
DEFAULT_YEARLY_LIMIT = 5
# 52 weeks ≈ 1 year of weekly recovery points. AzureWorkload (SAP HANA,
# SQL-on-VM) policies frequently default to 104; trimming the tail
# materially reduces storage with no RPO impact past month 6.
DEFAULT_WEEKLY_LIMIT = 52

# GRS → LRS switch: published price ratio is ~2.0; we apply a 30–50%
# headline of the vault's 30-day spend to leave margin for the
# protected-instance fee (which does not move with redundancy).
DEFAULT_GRS_LOW_FACTOR = 0.30
DEFAULT_GRS_HIGH_FACTOR = 0.50

# Retention bloat: yearly points dominate storage past month 24; trimming
# the tail is conservatively worth 20–40% of the vault spend.
DEFAULT_RETENTION_LOW_FACTOR = 0.20
DEFAULT_RETENTION_HIGH_FACTOR = 0.40

_TEST_NAME_RE = re.compile(
    r"\b(test|dev|staging|stage|uat|sandbox|sbox|qa)\b", re.IGNORECASE
)
_BACKUP_METER_CATEGORY = "Backup"


def _consumption_rows(consumption: object) -> list[dict]:
    if isinstance(consumption, list):
        return consumption
    if isinstance(consumption, dict):
        rows = consumption.get("actual")
        if isinstance(rows, list):
            return rows
    return []


def _vault_30d_gbp(consumption: object, vault_id: str) -> Decimal | None:
    rows = _consumption_rows(consumption)
    if not rows or not vault_id:
        return None
    target = vault_id.lower()
    total = Decimal("0")
    saw_match = False
    for row in rows:
        if not isinstance(row, dict):
            continue
        meter = row.get("MeterCategory") or row.get("meter_category")
        if meter != _BACKUP_METER_CATEGORY:
            continue
        rid = (row.get("ResourceId") or row.get("resource_id") or "").lower()
        if rid != target:
            continue
        currency = (row.get("Currency") or row.get("currency") or "").upper()
        if currency != "GBP":
            continue
        cost = row.get("Cost") if "Cost" in row else row.get("cost")
        try:
            total += Decimal(str(cost))
            saw_match = True
        except Exception:
            continue
    if not saw_match:
        return None
    return total


def _storage_type(vault: dict) -> str:
    """Prefer the `backup_properties.storageType` we collect via
    `az backup vault backup-properties show` (always populated). Fall back
    to `properties.storageType` (sometimes None on `az backup vault list`).
    """
    bp = vault.get("backup_properties") or {}
    storage = bp.get("storageType")
    if storage:
        return str(storage).strip()
    props = vault.get("properties") or {}
    return str(props.get("storageType") or "").strip()


def _soft_delete_state(vault: dict) -> str:
    props = vault.get("properties") or {}
    sec = props.get("securitySettings") or {}
    sd = sec.get("softDeleteSettings") or {}
    return str(
        sd.get("softDeleteState")
        or props.get("softDeleteFeatureState")
        or ""
    ).strip()


def _retention_count(schedule: dict) -> int | None:
    if not isinstance(schedule, dict):
        return None
    rd = schedule.get("retentionDuration") or {}
    v = rd.get("count")
    if v is None:
        return None
    try:
        return int(v)
    except (TypeError, ValueError):
        return None


def _max_retention_from(rp: dict) -> dict[str, int | None]:
    return {
        "daily": _retention_count(rp.get("dailySchedule") or {}),
        "weekly": _retention_count(rp.get("weeklySchedule") or {}),
        "monthly": _retention_count(rp.get("monthlySchedule") or {}),
        "yearly": _retention_count(rp.get("yearlySchedule") or {}),
    }


def _policy_retention(policy: dict) -> dict[str, int | None]:
    """Extract retention bands from a policy, handling both the AzureIaasVM
    shape (`properties.retentionPolicy`) and the AzureWorkload shape
    (`properties.subProtectionPolicy[].retentionPolicy`, e.g. SAP HANA,
    SQL-on-VM). For workload policies we take the **maximum** count across
    sub-policies — that's the value driving the storage line.
    """
    props = policy.get("properties") or {}
    candidates: list[dict[str, int | None]] = []
    direct = props.get("retentionPolicy") or {}
    if direct:
        candidates.append(_max_retention_from(direct))
    for sub in props.get("subProtectionPolicy") or []:
        if isinstance(sub, dict):
            sub_rp = sub.get("retentionPolicy") or {}
            if sub_rp:
                candidates.append(_max_retention_from(sub_rp))
    if not candidates:
        return {"daily": None, "weekly": None, "monthly": None, "yearly": None}
    out: dict[str, int | None] = {"daily": None, "weekly": None, "monthly": None, "yearly": None}
    for c in candidates:
        for k, v in c.items():
            if v is None:
                continue
            cur = out[k]
            out[k] = v if cur is None else max(cur, v)
    return out


def _is_test_shaped_sub(name: str) -> bool:
    return bool(name and _TEST_NAME_RE.search(name))


def _bloated_policies(
    policies: list[dict],
    monthly_limit: int,
    yearly_limit: int,
    weekly_limit: int,
) -> list[tuple[str, dict[str, int | None]]]:
    """Return [(policy_name, retention_dict)] for each policy exceeding
    monthly_limit OR yearly_limit OR weekly_limit. Policies without any of
    these schedules (typical short-term-only policies) are skipped silently.
    """
    flagged: list[tuple[str, dict[str, int | None]]] = []
    for pol in policies or []:
        if not isinstance(pol, dict):
            continue
        ret = _policy_retention(pol)
        weekly = ret.get("weekly")
        monthly = ret.get("monthly")
        yearly = ret.get("yearly")
        over_weekly = isinstance(weekly, int) and weekly > weekly_limit
        over_monthly = isinstance(monthly, int) and monthly > monthly_limit
        over_yearly = isinstance(yearly, int) and yearly > yearly_limit
        if over_weekly or over_monthly or over_yearly:
            flagged.append((str(pol.get("name") or "<unnamed>"), ret))
    return flagged


def evaluate(ctx: RuleContext) -> Iterable[Finding]:
    findings: list[Finding] = []
    monthly_limit = int(ctx.config.get("rsv_monthly_limit", DEFAULT_MONTHLY_LIMIT))
    yearly_limit = int(ctx.config.get("rsv_yearly_limit", DEFAULT_YEARLY_LIMIT))
    weekly_limit = int(ctx.config.get("rsv_weekly_limit", DEFAULT_WEEKLY_LIMIT))
    grs_low = float(ctx.config.get("rsv_grs_low_factor", DEFAULT_GRS_LOW_FACTOR))
    grs_high = float(ctx.config.get("rsv_grs_high_factor", DEFAULT_GRS_HIGH_FACTOR))
    ret_low = float(ctx.config.get("rsv_retention_low_factor", DEFAULT_RETENTION_LOW_FACTOR))
    ret_high = float(ctx.config.get("rsv_retention_high_factor", DEFAULT_RETENTION_HIGH_FACTOR))

    for sub in ctx.subscriptions():
        vaults = ctx.data_for(sub.id, "recovery_services")
        if vaults is None:
            findings.append(
                info_missing_data(
                    rule_id=RULE_ID,
                    title="Recovery Services Vaults",
                    subscription=sub,
                    missing_collector="recovery_services",
                )
            )
            continue
        consumption = ctx.data_for(sub.id, "consumption")
        sub_is_test = _is_test_shaped_sub(sub.name)

        for vault in vaults:
            if not isinstance(vault, dict):
                continue
            vault_id = vault.get("id") or ""
            vault_name = vault.get("name") or vault_id.rsplit("/", 1)[-1] or "unknown"
            location = vault.get("location")
            spend_30d = _vault_30d_gbp(consumption, vault_id)
            storage_type = _storage_type(vault)
            policies = vault.get("policies") or []

            # --- GRS storage ----------------------------------------------------
            # Flag GRS on **any** vault with consumption attribution. The case
            # for paying for cross-region replication is workload-specific, so
            # the rule surfaces every GRS vault for review and lets the operator
            # validate against their DR contract.
            #
            # Severity tiering:
            #   - non-prod-named subscription          → Medium
            #   - prod-named subscription, ≥ £20/mo    → Medium
            #   - prod-named subscription, < £20/mo    → Low
            #   - no consumption attribution           → Low (governance flag)
            if storage_type.lower() == "georedundant":
                estimated = None
                if spend_30d and spend_30d > 0:
                    estimated = savings_range(
                        round(float(spend_30d) * grs_low, 2),
                        round(float(spend_30d) * grs_high, 2),
                        assumption=(
                            f"30-day vault spend on this GeoRedundant vault is "
                            f"£{spend_30d:.0f}. Microsoft's published GRS/LRS "
                            f"storage ratio is ~2.0; the band applies "
                            f"{grs_low*100:.0f}–{grs_high*100:.0f}% to leave "
                            f"margin for the protected-instance fee, which does "
                            f"not move with redundancy. Net out any compliance "
                            f"clause that pins cross-region replication before "
                            f"booking the saving."
                        ),
                    )
                if sub_is_test:
                    severity = Severity.MEDIUM
                    title_qualifier = "non-prod"
                elif spend_30d is not None and spend_30d >= 20:
                    severity = Severity.MEDIUM
                    title_qualifier = "review-required"
                else:
                    severity = Severity.LOW
                    title_qualifier = "review-required"
                findings.append(
                    Finding(
                        rule_id=RULE_ID,
                        title=(
                            f"GeoRedundant backup ({title_qualifier}): {vault_name} "
                            f"(subscription '{sub.name}')"
                        ),
                        subscription_id=sub.id,
                        subscription_name=sub.name,
                        region=location,
                        resource_id=vault_id,
                        resource_name=vault_name,
                        severity=severity,
                        confidence=Confidence.MEDIUM,
                        estimated_savings=estimated,
                        knowledge_refs=KNOWLEDGE_REFS,
                        evidence={
                            "storage_type": storage_type,
                            "subscription_name_match": sub.name,
                            "subscription_is_test_shaped": sub_is_test,
                            "soft_delete_state": _soft_delete_state(vault) or None,
                        },
                        recommended_investigation=(
                            "Confirm the workloads protected by this vault need "
                            "cross-region recovery — many tenants don't, "
                            "especially for non-production or short-RPO data. "
                            "Switching the vault to LocallyRedundant cuts the "
                            "storage line by ~50% (Microsoft published rates). "
                            "ZoneRedundant is a middle option that retains in-"
                            "region zone failover at lower cost than GRS. "
                            "Note: redundancy can only be changed on a vault "
                            "with no protected items registered — plan a "
                            "drain-and-reprotect window before switching."
                        ),
                    )
                )

            # --- retention_bloat -----------------------------------------------
            bloated = _bloated_policies(policies, monthly_limit, yearly_limit, weekly_limit)
            if bloated:
                policy_summary = "; ".join(
                    f"{name} (weekly={ret['weekly']}, monthly={ret['monthly']}, yearly={ret['yearly']})"
                    for name, ret in bloated
                )
                estimated = None
                if spend_30d and spend_30d > 0:
                    estimated = savings_range(
                        round(float(spend_30d) * ret_low, 2),
                        round(float(spend_30d) * ret_high, 2),
                        assumption=(
                            f"30-day vault spend is £{spend_30d:.0f}. Yearly "
                            f"recovery points dominate storage past month 24; "
                            f"the band applies {ret_low*100:.0f}–"
                            f"{ret_high*100:.0f}% as the share recoverable by "
                            f"trimming the tail without affecting RPO/RTO for "
                            f"recent recovery."
                        ),
                    )
                findings.append(
                    Finding(
                        rule_id=RULE_ID,
                        title=(
                            f"Backup retention bloat on vault {vault_name}: "
                            f"{policy_summary}"
                        ),
                        subscription_id=sub.id,
                        subscription_name=sub.name,
                        region=location,
                        resource_id=vault_id,
                        resource_name=vault_name,
                        severity=Severity.MEDIUM,
                        confidence=Confidence.MEDIUM,
                        estimated_savings=estimated,
                        knowledge_refs=KNOWLEDGE_REFS,
                        evidence={
                            "storage_type": storage_type or None,
                            "weekly_limit_used": weekly_limit,
                            "monthly_limit_used": monthly_limit,
                            "yearly_limit_used": yearly_limit,
                            "flagged_policies": [
                                {"name": name, **{k: v for k, v in ret.items()}}
                                for name, ret in bloated
                            ],
                        },
                        recommended_investigation=(
                            "Confirm with the data owner what audit / "
                            "compliance contract pins yearly retention. Most "
                            "SOC 2 / ISO 27001 / HIPAA contracts cap total "
                            "retention at ≤7 years, far below Azure's portal "
                            "default of 60 monthly + 10 yearly recovery "
                            "points. Trimming the tail is a policy edit on the "
                            "vault — existing recovery points outside the new "
                            "window are pruned on the next backup cycle."
                        ),
                    )
                )
    return findings
