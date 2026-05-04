"""Tests for the dev_test_offer_eligibility rule.

Detects subscriptions that are *named or tagged* as non-prod but are still
running on a non-DevTest quotaId. The savings band derives from the
consumption snapshot's 30-day VM compute total (MeterCategory == "Virtual
Machines"), bounded at 20–40% of that total.
"""

from __future__ import annotations

from azure_cost_investigator.rules import dev_test_offer_eligibility as rule
from azure_cost_investigator.rules.base import RuleContext
from azure_investigator_core.schema import Severity


def _sub_record(quota_id: str | None) -> list[dict]:
    if quota_id is None:
        return [{"id": "x", "subscription_policies": None}]
    return [
        {
            "id": "x",
            "subscription_policies": {
                "quota_id": quota_id,
                "spending_limit": "Off",
                "location_placement_id": "Internal_2014-09-01",
            },
        }
    ]


def _vm_compute_consumption(total_gbp: float) -> dict:
    """Build a consumption payload whose Virtual Machines rows sum to total_gbp."""
    rows = [
        {
            "Cost": total_gbp,
            "UsageDate": 20260401,
            "ResourceId": "/sub/x/vm/A",
            "ServiceName": "Virtual Machines",
            "MeterCategory": "Virtual Machines",
            "ChargeType": "Usage",
            "Currency": "GBP",
        }
    ]
    return {"window_start": "2026-04-01", "window_end": "2026-04-30", "actual": rows}


def test_test_named_sub_on_payg_quota_is_flagged_with_band(
    snapshot_factory, cost_knowledge
):
    paths = snapshot_factory(
        {
            "sub-1": {
                "subscriptions": _sub_record("PayAsYouGo_2014-09-01"),
                "consumption": _vm_compute_consumption(2000.0),
            }
        },
        sub_names={"sub-1": "ACME-IT-TEST"},
    )
    ctx = RuleContext.from_snapshot(paths, cost_knowledge)
    (f,) = list(rule.evaluate(ctx))
    assert f.severity == Severity.HIGH
    # 2000 × 0.20 = 400 low, 2000 × 0.40 = 800 high.
    assert float(f.estimated_savings.low_gbp_per_month) == 400.0
    assert float(f.estimated_savings.high_gbp_per_month) == 800.0
    assert f.evidence["quota_id"] == "PayAsYouGo_2014-09-01"
    assert "non-prod pattern" in f.evidence["test_shape_reason"]


def test_devtest_quota_is_not_flagged(snapshot_factory, cost_knowledge):
    # The whole point of the rule: if the sub is already on Dev/Test,
    # there's nothing to recommend.
    paths = snapshot_factory(
        {
            "sub-1": {
                "subscriptions": _sub_record("MSDNDevTest_2014-09-01"),
                "consumption": _vm_compute_consumption(2000.0),
            }
        },
        sub_names={"sub-1": "ACME-IT-TEST"},
    )
    ctx = RuleContext.from_snapshot(paths, cost_knowledge)
    assert list(rule.evaluate(ctx)) == []


def test_ea_devtest_quota_is_recognised(snapshot_factory, cost_knowledge):
    paths = snapshot_factory(
        {
            "sub-1": {
                "subscriptions": _sub_record("EnterpriseAgreement_DevTest_2014-09-01"),
                "consumption": _vm_compute_consumption(2000.0),
            }
        },
        sub_names={"sub-1": "ACME-IT-TEST"},
    )
    ctx = RuleContext.from_snapshot(paths, cost_knowledge)
    assert list(rule.evaluate(ctx)) == []


def test_prod_named_sub_on_payg_is_not_flagged(snapshot_factory, cost_knowledge):
    # No "test"/"dev"/"staging"/"uat" hint in the sub name and no env tag
    # on VMs → cannot infer eligibility, so don't flag.
    paths = snapshot_factory(
        {
            "sub-1": {
                "subscriptions": _sub_record("PayAsYouGo_2014-09-01"),
                "consumption": _vm_compute_consumption(2000.0),
                "vms": [],
            }
        },
        sub_names={"sub-1": "ACME-IT-PROD"},
    )
    ctx = RuleContext.from_snapshot(paths, cost_knowledge)
    assert list(rule.evaluate(ctx)) == []


def test_majority_test_tagged_vms_triggers_even_without_test_in_name(
    snapshot_factory, cost_knowledge
):
    # Sub is named "platform" (no obvious non-prod hint) but >50% of its
    # VMs carry environment=test → still flag, because the workload signal
    # is unambiguous.
    vms = [
        {"id": f"/vm/{i}", "name": f"vm-{i}", "tags": {"environment": "test"}}
        for i in range(3)
    ] + [{"id": "/vm/x", "name": "vm-x", "tags": {"environment": "prod"}}]
    paths = snapshot_factory(
        {
            "sub-1": {
                "subscriptions": _sub_record("PayAsYouGo_2014-09-01"),
                "consumption": _vm_compute_consumption(1000.0),
                "vms": vms,
            }
        },
        sub_names={"sub-1": "platform-shared"},
    )
    ctx = RuleContext.from_snapshot(paths, cost_knowledge)
    (f,) = list(rule.evaluate(ctx))
    assert f.severity == Severity.HIGH
    assert "3 of 4 VMs" in f.evidence["test_shape_reason"]


def test_no_consumption_data_emits_finding_without_band(
    snapshot_factory, cost_knowledge
):
    # If the consumption collector didn't run, we still want to surface the
    # procurement action — the £ band is a bonus, not a precondition.
    paths = snapshot_factory(
        {
            "sub-1": {
                "subscriptions": _sub_record("PayAsYouGo_2014-09-01"),
                "consumption": None,
            }
        },
        sub_names={"sub-1": "ACME-IT-TEST"},
    )
    ctx = RuleContext.from_snapshot(paths, cost_knowledge)
    (f,) = list(rule.evaluate(ctx))
    assert f.severity == Severity.HIGH
    assert f.estimated_savings is None


def test_missing_quota_id_emits_info(snapshot_factory, cost_knowledge):
    paths = snapshot_factory(
        {"sub-1": {"subscriptions": _sub_record(None)}},
        sub_names={"sub-1": "ACME-IT-TEST"},
    )
    ctx = RuleContext.from_snapshot(paths, cost_knowledge)
    (f,) = list(rule.evaluate(ctx))
    assert f.severity == Severity.INFO


def test_factors_are_overridable_via_config(snapshot_factory, cost_knowledge):
    paths = snapshot_factory(
        {
            "sub-1": {
                "subscriptions": _sub_record("PayAsYouGo_2014-09-01"),
                "consumption": _vm_compute_consumption(1000.0),
            }
        },
        sub_names={"sub-1": "ACME-IT-TEST"},
    )
    ctx = RuleContext.from_snapshot(paths, cost_knowledge)
    ctx.config["dev_test_low_factor"] = 0.30
    ctx.config["dev_test_high_factor"] = 0.55
    (f,) = list(rule.evaluate(ctx))
    assert float(f.estimated_savings.low_gbp_per_month) == 300.0
    assert float(f.estimated_savings.high_gbp_per_month) == 550.0


def test_only_vm_meter_category_counts(snapshot_factory, cost_knowledge):
    # Storage and SQL line items must not pollute the VM compute total.
    rows = [
        {
            "Cost": 100.0,
            "MeterCategory": "Storage",
            "Currency": "GBP",
            "UsageDate": 20260401,
            "ResourceId": "/x",
            "ServiceName": "Storage",
            "ChargeType": "Usage",
        },
        {
            "Cost": 500.0,
            "MeterCategory": "Virtual Machines",
            "Currency": "GBP",
            "UsageDate": 20260401,
            "ResourceId": "/y",
            "ServiceName": "Virtual Machines",
            "ChargeType": "Usage",
        },
    ]
    paths = snapshot_factory(
        {
            "sub-1": {
                "subscriptions": _sub_record("PayAsYouGo_2014-09-01"),
                "consumption": {
                    "window_start": "x",
                    "window_end": "y",
                    "actual": rows,
                },
            }
        },
        sub_names={"sub-1": "ACME-IT-TEST"},
    )
    ctx = RuleContext.from_snapshot(paths, cost_knowledge)
    (f,) = list(rule.evaluate(ctx))
    # Band based on £500 VM compute only → 100–200, not 120–240.
    assert float(f.estimated_savings.low_gbp_per_month) == 100.0
    assert float(f.estimated_savings.high_gbp_per_month) == 200.0


def test_knowledge_refs_present(cost_knowledge):
    for ref in rule.KNOWLEDGE_REFS:
        assert cost_knowledge.has(ref)
