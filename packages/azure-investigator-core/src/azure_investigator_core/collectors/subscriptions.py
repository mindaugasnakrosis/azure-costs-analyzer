"""Subscription metadata + offer/quota detection.

`az account show` returns the orchestrator's view (state, tenant, name) but
omits `subscriptionPolicies.quotaId` — the field that distinguishes a
Dev/Test offer (`MSDNDevTest_*`, `EnterpriseAgreement_DevTest_*`,
`PayAsYouGoDevTest_*`) from a full PAYG/EA offer. The Dev/Test offer is
worth up to 55% off Windows VM compute and removes Windows/SQL Server
licensing on eligible workloads, so the rule layer needs the quotaId to
flag a "test"-named subscription that's still on full PAYG rates.

We make a second call to `az account subscription show --id <id>` (the
Microsoft.Subscription resource provider's Get Subscription API) and merge
the relevant policy fields onto the record. If the second call fails the
record is still emitted with `subscription_policies = None`; the rule
layer downgrades to Info on missing data rather than skipping the sub.
"""

from __future__ import annotations

from . import CollectorOutput, safe_run_json

NAME = "subscriptions"


def collect(subscription_id: str) -> CollectorOutput:
    out = safe_run_json(["account", "show", "--subscription", subscription_id])
    if out.error or out.data is None:
        return out

    # The `az account subscription show` shim through the
    # Microsoft.Subscription resource provider is slow/flaky for some
    # tenants — we've measured 60+ seconds with no response. Hit the ARM
    # endpoint directly first (always fast); fall back to the legacy CLI
    # path only if `az rest` returns an unexpected shape.
    arm_call = safe_run_json(
        [
            "rest",
            "--method",
            "get",
            "--url",
            f"https://management.azure.com/subscriptions/{subscription_id}?api-version=2022-12-01",
        ],
        timeout=20.0,
    )
    policies_call = arm_call
    if arm_call.error or not isinstance(arm_call.data, dict):
        policies_call = safe_run_json(
            ["account", "subscription", "show", "--id", subscription_id],
            timeout=30.0,
        )
    record = dict(out.data)
    if policies_call.data is not None:
        sub_policies = (policies_call.data or {}).get("subscriptionPolicies") or {}
        record["subscription_policies"] = {
            "quota_id": sub_policies.get("quotaId"),
            "spending_limit": sub_policies.get("spendingLimit"),
            "location_placement_id": sub_policies.get("locationPlacementId"),
        }
    elif policies_call.error:
        record["subscription_policies"] = None
        record["_subscription_policies_error"] = policies_call.error

    return CollectorOutput.ok([record])
