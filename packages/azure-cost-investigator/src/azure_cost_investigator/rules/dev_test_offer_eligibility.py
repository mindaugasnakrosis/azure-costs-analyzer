"""dev_test_offer_eligibility — flag a "test"-shaped subscription that is
running on a full PAYG/EA quotaId rather than the Dev/Test offer.

Microsoft's Dev/Test pricing strips Windows Server licensing on VMs (giving
the Linux compute rate to Windows VMs — up to ~55% off) and reduces SQL
Server VM and SQL Database licensing on non-production workloads. The
decision to enrol a subscription on Dev/Test is a one-shot procurement
action by the EA admin or billing owner; this rule surfaces it as such,
not as a per-resource action.

Authority: `dev-test-offer.md`. The detection signal is purely
`subscriptionPolicies.quotaId` from the subscriptions collector + the
subscription's display name. The savings band is derived from the
consumption snapshot (`MeterCategory == "Virtual Machines"` 30-day total)
multiplied by a deliberately conservative 20–40% factor — Microsoft's
published headline is "up to 55%" but only on Windows VM compute, and we
can't tell from the snapshot what fraction of compute is Windows.
"""

from __future__ import annotations

import re
from collections.abc import Iterable
from decimal import Decimal

from azure_investigator_core.schema import Confidence, Finding, Severity

from .base import RuleContext, savings_range

RULE_ID = "dev_test_offer_eligibility"
KNOWLEDGE_REFS = ["dev-test-offer.md", "pricing-sources.md"]

# quotaId fragments that indicate a Dev/Test offer is already in effect.
# Match is case-insensitive and substring-based to absorb minor naming drift
# across offer generations (MSDNDevTest_2014-09-01, MSDN_DevTest_2014-09-01,
# EnterpriseAgreement_DevTest_2014-09-01, PayAsYouGoDevTest_*, etc.).
_DEVTEST_QUOTA_FRAGMENTS = ("devtest", "msdn", "sponsored", "mpn")

# Test-shaped subscription / tag value pattern. Word-boundary match on common
# non-prod tokens so we don't false-positive on e.g. "westus".
_TEST_NAME_RE = re.compile(r"\b(test|dev|staging|stage|uat|sandbox|sbox|qa)\b", re.IGNORECASE)

# Conservative band on the headline Microsoft figure. See knowledge file.
DEFAULT_LOW_FACTOR = 0.20
DEFAULT_HIGH_FACTOR = 0.40

_VM_METER_CATEGORY = "Virtual Machines"


def _is_devtest_quota(quota_id: str | None) -> bool:
    if not quota_id:
        return False
    q = quota_id.lower()
    return any(fragment in q for fragment in _DEVTEST_QUOTA_FRAGMENTS)


def _vm_tag_env_is_testlike(vm: dict) -> bool:
    tags = vm.get("tags") or {}
    for key in ("environment", "env", "Environment", "Env"):
        v = tags.get(key)
        if isinstance(v, str) and _TEST_NAME_RE.search(v):
            return True
    return False


def _is_test_shaped(sub_name: str, vms: list[dict] | None) -> tuple[bool, str]:
    if sub_name and _TEST_NAME_RE.search(sub_name):
        return True, f"subscription name '{sub_name}' matches non-prod pattern"
    if vms:
        flagged = sum(1 for vm in vms if _vm_tag_env_is_testlike(vm))
        if flagged and flagged * 2 > len(vms):
            return True, (
                f"{flagged} of {len(vms)} VMs carry an environment tag "
                f"matching the non-prod pattern"
            )
    return False, ""


def _consumption_rows(consumption: object) -> list[dict]:
    """Extract the row list from the consumption collector's payload.

    The collector emits a dict `{actual, amortised, window_start, ...}` where
    `actual` is the daily ChargeType=Usage rows. Older or stub payloads may
    be a flat list; handle both.
    """
    if isinstance(consumption, list):
        return consumption
    if isinstance(consumption, dict):
        rows = consumption.get("actual")
        if isinstance(rows, list):
            return rows
    return []


def _vm_compute_30d_gbp(consumption: object) -> Decimal | None:
    """Sum 30-day VM compute spend from the consumption snapshot.

    Sums `Cost` over rows where `MeterCategory == "Virtual Machines"` and
    `Currency == "GBP"`. The snapshot is pulled in tenant currency so a
    non-GBP row is either a stub or a tenant on a different billing
    currency; in the latter case we refuse to estimate rather than mix.
    """
    rows = _consumption_rows(consumption)
    if not rows:
        return None
    total = Decimal("0")
    saw_gbp = False
    for row in rows:
        if not isinstance(row, dict):
            continue
        if (row.get("meter_category") or row.get("MeterCategory")) != _VM_METER_CATEGORY:
            continue
        currency = (row.get("currency") or row.get("Currency") or "").upper()
        if currency != "GBP":
            continue
        saw_gbp = True
        cost = row.get("cost") if "cost" in row else row.get("Cost")
        try:
            total += Decimal(str(cost))
        except Exception:
            continue
    if not saw_gbp:
        return None
    return total


def evaluate(ctx: RuleContext) -> Iterable[Finding]:
    findings: list[Finding] = []
    low_factor = float(ctx.config.get("dev_test_low_factor", DEFAULT_LOW_FACTOR))
    high_factor = float(ctx.config.get("dev_test_high_factor", DEFAULT_HIGH_FACTOR))

    for sub in ctx.subscriptions():
        sub_records = ctx.data_for(sub.id, "subscriptions") or []
        if not sub_records:
            continue
        sub_record = sub_records[0] if isinstance(sub_records, list) else sub_records
        policies = sub_record.get("subscription_policies") or {}
        quota_id = policies.get("quota_id")
        if quota_id is None:
            # The subscriptions collector ran before this field was added,
            # or the second az call was refused. Surface as Info rather than
            # silently passing — the user needs to know detection is blind.
            findings.append(
                Finding(
                    rule_id=RULE_ID,
                    title=f"Dev/Test offer check — quotaId unavailable for {sub.name}",
                    subscription_id=sub.id,
                    subscription_name=sub.name,
                    severity=Severity.INFO,
                    confidence=Confidence.HIGH,
                    knowledge_refs=[],
                    evidence={
                        "subscription_policies": policies or None,
                        "error": sub_record.get("_subscription_policies_error"),
                    },
                    recommended_investigation=(
                        "The subscriptions collector did not return a "
                        "subscription quotaId. Re-run pull after granting the "
                        "runner identity Reader on the subscription, or run "
                        "`az account subscription show --id <sub>` manually "
                        "and verify the offer."
                    ),
                )
            )
            continue
        if _is_devtest_quota(quota_id):
            continue

        vms = ctx.data_for(sub.id, "vms")
        is_test, reason = _is_test_shaped(sub.name, vms)
        if not is_test:
            continue

        consumption = ctx.data_for(sub.id, "consumption")
        compute_30d = _vm_compute_30d_gbp(consumption)
        estimated_savings = None
        compute_basis: str | None = None
        if compute_30d and compute_30d > 0:
            compute_basis = f"£{compute_30d:.0f}/30d VM compute"
            estimated_savings = savings_range(
                round(float(compute_30d) * low_factor, 2),
                round(float(compute_30d) * high_factor, 2),
                assumption=(
                    f"30-day VM compute spend on this subscription is "
                    f"£{compute_30d:.0f}. Band applies {low_factor*100:.0f}–"
                    f"{high_factor*100:.0f}% as the achievable Dev/Test "
                    f"discount: Microsoft publishes 'up to 55%' on Windows VM "
                    f"compute, but the snapshot doesn't reveal the "
                    f"Windows/Linux mix or which workloads qualify under the "
                    f"licence terms. Net out any RI/SP coverage before "
                    f"booking the saving — Dev/Test enrolment doesn't stack "
                    f"with reservations on the same hours."
                ),
            )

        is_csp = quota_id.lower().startswith("csp_")
        if is_csp:
            channel_action = (
                "ask the **CSP partner** (whoever sells the tenant Azure) "
                "whether they can re-provision the subscription on a "
                "CSP_DevTest_* offer; CSP is a partner-billed channel, so "
                "the change is a partner action, not an EA admin action"
            )
        else:
            channel_action = (
                "ask the EA / billing admin to convert the subscription "
                "to the Dev/Test offer in the Azure portal: Cost Management + "
                "Billing → Subscriptions → (sub) → Change offer"
            )
        findings.append(
            Finding(
                rule_id=RULE_ID,
                title=(
                    f"Subscription on full PAYG/EA/CSP but appears non-prod: "
                    f"{sub.name} (quotaId: {quota_id})"
                ),
                subscription_id=sub.id,
                subscription_name=sub.name,
                severity=Severity.HIGH,
                confidence=Confidence.MEDIUM,
                estimated_savings=estimated_savings,
                knowledge_refs=KNOWLEDGE_REFS,
                evidence={
                    "quota_id": quota_id,
                    "billing_channel": "CSP" if is_csp else "EA/PAYG",
                    "test_shape_reason": reason,
                    "compute_basis": compute_basis,
                },
                recommended_investigation=(
                    "If the workloads on this subscription are genuinely "
                    "non-production (no end-user traffic, restricted to "
                    "Visual Studio subscribers), "
                    f"{channel_action}. Confirm the tenant has Dev/Test "
                    "eligibility on its enrolment first; the offer is "
                    "contractual, not a feature flag, and Microsoft can "
                    "audit usage. The £ band assumes a Windows-heavy mix; "
                    "Linux-only subscriptions see no compute discount and "
                    "only benefit on SQL DB Dev/Test SKUs."
                ),
            )
        )
    return findings
