"""Tests for the rsv_backup_retention rule."""

from __future__ import annotations

from azure_cost_investigator.rules import rsv_backup_retention as rule
from azure_cost_investigator.rules.base import RuleContext
from azure_investigator_core.schema import Severity


def _vault(
    name="vault1",
    *,
    storage_type: str = "GeoRedundant",
    location: str = "uksouth",
    policies: list[dict] | None = None,
    soft_delete: str | None = None,
) -> dict:
    vault_id = f"/subscriptions/sub-1/resourceGroups/rg/providers/microsoft.recoveryservices/vaults/{name}"
    props: dict = {"storageType": storage_type}
    if soft_delete is not None:
        props["securitySettings"] = {"softDeleteSettings": {"softDeleteState": soft_delete}}
    return {
        "id": vault_id,
        "name": name,
        "location": location,
        "properties": props,
        "policies": policies or [],
    }


def _policy(name: str, *, daily=7, weekly=4, monthly=12, yearly=5) -> dict:
    def _sched(count: int | None) -> dict:
        return {"retentionDuration": {"count": count}} if count is not None else {}

    return {
        "name": name,
        "properties": {
            "retentionPolicy": {
                "dailySchedule": _sched(daily),
                "weeklySchedule": _sched(weekly),
                "monthlySchedule": _sched(monthly),
                "yearlySchedule": _sched(yearly),
            }
        },
    }


def _consumption_for(vault_id: str, gbp: float) -> dict:
    return {
        "actual": [
            {
                "Cost": gbp,
                "MeterCategory": "Backup",
                "Currency": "GBP",
                "ResourceId": vault_id,
                "UsageDate": 20260401,
                "ServiceName": "Backup",
                "ChargeType": "Usage",
            }
        ]
    }


def test_within_limits_on_prod_sub_is_not_flagged(snapshot_factory, cost_knowledge):
    v = _vault(storage_type="LocallyRedundant", policies=[_policy("p", monthly=12, yearly=5)])
    paths = snapshot_factory(
        {"sub-1": {"recovery_services": [v]}},
        sub_names={"sub-1": "prod-payments"},
    )
    ctx = RuleContext.from_snapshot(paths, cost_knowledge)
    assert list(rule.evaluate(ctx)) == []


def test_grs_on_nonprod_sub_is_flagged(snapshot_factory, cost_knowledge):
    v = _vault(storage_type="GeoRedundant", policies=[_policy("p", monthly=12, yearly=5)])
    paths = snapshot_factory(
        {"sub-1": {"recovery_services": [v]}},
        sub_names={"sub-1": "acme-it-test"},
    )
    ctx = RuleContext.from_snapshot(paths, cost_knowledge)
    findings = list(rule.evaluate(ctx))
    assert len(findings) == 1
    assert findings[0].severity == Severity.MEDIUM
    assert "GeoRedundant" in findings[0].title


def test_grs_on_prod_sub_without_consumption_is_low(snapshot_factory, cost_knowledge):
    # No consumption attribution → governance flag at Low severity.
    v = _vault(storage_type="GeoRedundant", policies=[_policy("p", monthly=12, yearly=5)])
    paths = snapshot_factory(
        {"sub-1": {"recovery_services": [v]}},
        sub_names={"sub-1": "prod-payments"},
    )
    ctx = RuleContext.from_snapshot(paths, cost_knowledge)
    findings = list(rule.evaluate(ctx))
    assert len(findings) == 1
    assert findings[0].severity == Severity.LOW
    assert "review-required" in findings[0].title
    assert findings[0].evidence["subscription_is_test_shaped"] is False


def test_grs_on_prod_sub_with_consumption_above_threshold_is_medium(
    snapshot_factory, cost_knowledge
):
    # Consumption ≥ £20/mo → Medium severity even on a prod sub. Real money.
    v = _vault(storage_type="GeoRedundant", policies=[_policy("p", monthly=12, yearly=5)])
    paths = snapshot_factory(
        {
            "sub-1": {
                "recovery_services": [v],
                "consumption": _consumption_for(v["id"], 100.0),
            }
        },
        sub_names={"sub-1": "prod-payments"},
    )
    ctx = RuleContext.from_snapshot(paths, cost_knowledge)
    findings = list(rule.evaluate(ctx))
    assert len(findings) == 1
    assert findings[0].severity == Severity.MEDIUM
    assert "review-required" in findings[0].title
    # 100 × 0.30 = 30, 100 × 0.50 = 50
    assert float(findings[0].estimated_savings.low_gbp_per_month) == 30.0
    assert float(findings[0].estimated_savings.high_gbp_per_month) == 50.0


def test_grs_on_prod_sub_with_tiny_consumption_is_low(snapshot_factory, cost_knowledge):
    # Consumption < £20/mo → Low severity (still surfaced as governance, but
    # not worth Medium attention).
    v = _vault(storage_type="GeoRedundant", policies=[_policy("p", monthly=12, yearly=5)])
    paths = snapshot_factory(
        {
            "sub-1": {
                "recovery_services": [v],
                "consumption": _consumption_for(v["id"], 5.0),
            }
        },
        sub_names={"sub-1": "prod-payments"},
    )
    ctx = RuleContext.from_snapshot(paths, cost_knowledge)
    findings = list(rule.evaluate(ctx))
    assert len(findings) == 1
    assert findings[0].severity == Severity.LOW


def test_retention_bloat_monthly_above_default_limit(snapshot_factory, cost_knowledge):
    v = _vault(
        storage_type="LocallyRedundant",
        policies=[_policy("EnhancedPolicy", monthly=60, yearly=5)],
    )
    paths = snapshot_factory(
        {"sub-1": {"recovery_services": [v]}},
        sub_names={"sub-1": "prod-payments"},
    )
    ctx = RuleContext.from_snapshot(paths, cost_knowledge)
    findings = list(rule.evaluate(ctx))
    assert len(findings) == 1
    assert "retention bloat" in findings[0].title.lower()
    assert findings[0].evidence["flagged_policies"][0]["monthly"] == 60


def test_retention_bloat_yearly_above_default_limit(snapshot_factory, cost_knowledge):
    v = _vault(
        storage_type="LocallyRedundant",
        policies=[_policy("p", monthly=12, yearly=10)],
    )
    paths = snapshot_factory(
        {"sub-1": {"recovery_services": [v]}},
        sub_names={"sub-1": "prod-payments"},
    )
    ctx = RuleContext.from_snapshot(paths, cost_knowledge)
    findings = list(rule.evaluate(ctx))
    assert len(findings) == 1
    assert findings[0].evidence["flagged_policies"][0]["yearly"] == 10


def test_band_derived_from_consumption_when_present(snapshot_factory, cost_knowledge):
    v = _vault(
        storage_type="LocallyRedundant",
        policies=[_policy("EnhancedPolicy", monthly=60, yearly=10)],
    )
    paths = snapshot_factory(
        {
            "sub-1": {
                "recovery_services": [v],
                "consumption": _consumption_for(v["id"], 500.0),
            }
        },
        sub_names={"sub-1": "prod-payments"},
    )
    ctx = RuleContext.from_snapshot(paths, cost_knowledge)
    (f,) = list(rule.evaluate(ctx))
    # 500 × 0.20 = 100, 500 × 0.40 = 200.
    assert float(f.estimated_savings.low_gbp_per_month) == 100.0
    assert float(f.estimated_savings.high_gbp_per_month) == 200.0


def test_grs_band_uses_grs_factors(snapshot_factory, cost_knowledge):
    v = _vault(storage_type="GeoRedundant", policies=[_policy("p", monthly=12, yearly=5)])
    paths = snapshot_factory(
        {
            "sub-1": {
                "recovery_services": [v],
                "consumption": _consumption_for(v["id"], 1000.0),
            }
        },
        sub_names={"sub-1": "test-sub"},
    )
    ctx = RuleContext.from_snapshot(paths, cost_knowledge)
    (f,) = list(rule.evaluate(ctx))
    # 1000 × 0.30 = 300, 1000 × 0.50 = 500.
    assert float(f.estimated_savings.low_gbp_per_month) == 300.0
    assert float(f.estimated_savings.high_gbp_per_month) == 500.0


def test_no_band_when_consumption_does_not_match_vault(snapshot_factory, cost_knowledge):
    v = _vault(
        storage_type="LocallyRedundant",
        policies=[_policy("p", monthly=60, yearly=5)],
    )
    paths = snapshot_factory(
        {
            "sub-1": {
                "recovery_services": [v],
                "consumption": _consumption_for("/different/vault", 500.0),
            }
        },
        sub_names={"sub-1": "prod-payments"},
    )
    ctx = RuleContext.from_snapshot(paths, cost_knowledge)
    (f,) = list(rule.evaluate(ctx))
    assert f.estimated_savings is None


def test_both_grs_and_retention_emit_two_findings(snapshot_factory, cost_knowledge):
    v = _vault(
        storage_type="GeoRedundant",
        policies=[_policy("EnhancedPolicy", monthly=60, yearly=10)],
    )
    paths = snapshot_factory(
        {"sub-1": {"recovery_services": [v]}},
        sub_names={"sub-1": "test-sub"},
    )
    ctx = RuleContext.from_snapshot(paths, cost_knowledge)
    findings = list(rule.evaluate(ctx))
    assert len(findings) == 2
    titles = {f.title for f in findings}
    assert any("GeoRedundant" in t for t in titles)
    assert any("retention bloat" in t.lower() for t in titles)


def test_missing_collector_emits_info(snapshot_factory, cost_knowledge):
    paths = snapshot_factory({"sub-1": {"recovery_services": None}})
    ctx = RuleContext.from_snapshot(paths, cost_knowledge)
    (f,) = list(rule.evaluate(ctx))
    assert f.severity == Severity.INFO


def test_factors_overridable_via_config(snapshot_factory, cost_knowledge):
    v = _vault(
        storage_type="LocallyRedundant",
        policies=[_policy("p", monthly=60, yearly=10)],
    )
    paths = snapshot_factory(
        {
            "sub-1": {
                "recovery_services": [v],
                "consumption": _consumption_for(v["id"], 1000.0),
            }
        },
        sub_names={"sub-1": "prod-payments"},
    )
    ctx = RuleContext.from_snapshot(paths, cost_knowledge)
    ctx.config["rsv_retention_low_factor"] = 0.30
    ctx.config["rsv_retention_high_factor"] = 0.50
    (f,) = list(rule.evaluate(ctx))
    assert float(f.estimated_savings.low_gbp_per_month) == 300.0
    assert float(f.estimated_savings.high_gbp_per_month) == 500.0


def test_limit_overrides_via_config(snapshot_factory, cost_knowledge):
    # Tighter limits expand what gets flagged.
    v = _vault(
        storage_type="LocallyRedundant",
        policies=[_policy("p", monthly=6, yearly=2)],
    )
    paths = snapshot_factory(
        {"sub-1": {"recovery_services": [v]}},
        sub_names={"sub-1": "prod-payments"},
    )
    ctx = RuleContext.from_snapshot(paths, cost_knowledge)
    ctx.config["rsv_monthly_limit"] = 3
    ctx.config["rsv_yearly_limit"] = 1
    findings = list(rule.evaluate(ctx))
    assert len(findings) == 1
    flagged = findings[0].evidence["flagged_policies"][0]
    assert flagged["monthly"] == 6
    assert flagged["yearly"] == 2


def test_policy_without_monthly_yearly_is_skipped(snapshot_factory, cost_knowledge):
    # Daily/weekly-only policy (e.g., short-term backup) should not flag.
    v = _vault(
        storage_type="LocallyRedundant",
        policies=[_policy("short-term", daily=7, weekly=4, monthly=None, yearly=None)],
    )
    paths = snapshot_factory(
        {"sub-1": {"recovery_services": [v]}},
        sub_names={"sub-1": "prod-payments"},
    )
    ctx = RuleContext.from_snapshot(paths, cost_knowledge)
    assert list(rule.evaluate(ctx)) == []


def test_workload_policy_subprotection_retention_is_walked(snapshot_factory, cost_knowledge):
    # AzureWorkload (SAP HANA / SQL-on-VM) policies put retention inside
    # subProtectionPolicy[].retentionPolicy rather than at the root.
    workload_policy = {
        "name": "HANALongRetention",
        "properties": {
            "backupManagementType": "AzureWorkload",
            "subProtectionPolicy": [
                {
                    "policyType": "Full",
                    "retentionPolicy": {
                        "weeklySchedule": {"retentionDuration": {"count": 104}},
                        "monthlySchedule": {"retentionDuration": {"count": 60}},
                        "yearlySchedule": {"retentionDuration": {"count": 10}},
                    },
                },
                {"policyType": "Differential", "retentionPolicy": None},
                {"policyType": "Log", "retentionPolicy": None},
            ],
        },
    }
    v = _vault(storage_type="LocallyRedundant", policies=[workload_policy])
    paths = snapshot_factory(
        {"sub-1": {"recovery_services": [v]}},
        sub_names={"sub-1": "prod-payments"},
    )
    ctx = RuleContext.from_snapshot(paths, cost_knowledge)
    findings = list(rule.evaluate(ctx))
    assert len(findings) == 1
    flagged = findings[0].evidence["flagged_policies"][0]
    assert flagged["weekly"] == 104
    assert flagged["monthly"] == 60
    assert flagged["yearly"] == 10


def test_weekly_above_default_limit_is_flagged(snapshot_factory, cost_knowledge):
    v = _vault(
        storage_type="LocallyRedundant",
        policies=[_policy("WeeklyHeavy", daily=None, weekly=104, monthly=None, yearly=None)],
    )
    paths = snapshot_factory(
        {"sub-1": {"recovery_services": [v]}},
        sub_names={"sub-1": "prod-payments"},
    )
    ctx = RuleContext.from_snapshot(paths, cost_knowledge)
    findings = list(rule.evaluate(ctx))
    assert len(findings) == 1
    assert findings[0].evidence["flagged_policies"][0]["weekly"] == 104


def test_knowledge_refs_present(cost_knowledge):
    for ref in rule.KNOWLEDGE_REFS:
        assert cost_knowledge.has(ref)
