from __future__ import annotations

from azure_cost_investigator.rules import dev_skus_in_prod as rule
from azure_cost_investigator.rules.base import RuleContext
from azure_investigator_core.schema import Severity


def _vm(name, sku, env=None):
    return {
        "id": f"/sub/vms/{name}",
        "name": name,
        "location": "uksouth",
        "powerState": "VM running",
        "hardwareProfile": {"vmSize": sku},
        "tags": {"env": env} if env else {},
    }


def _asp(name, tier, env=None):
    return {
        "id": f"/sub/asps/{name}",
        "name": name,
        "location": "uksouth",
        "sku": {"tier": tier, "name": "?"},
        "numberOfSites": 1,
        "tags": {"env": env} if env else {},
    }


def test_flags_dev_sku_on_prod_tagged_vm(snapshot_factory, cost_knowledge):
    vms = [
        _vm("undersized-prod", "Standard_B1s", env="prod"),
        _vm("ok-prod", "Standard_D4s_v5", env="prod"),
    ]
    paths = snapshot_factory({"sub-1": {"vms": vms, "app_service_plans": []}})
    ctx = RuleContext.from_snapshot(paths, cost_knowledge)
    findings = list(rule.evaluate(ctx))
    titles = [f.title for f in findings]
    assert any("undersized-prod" in t for t in titles)
    assert all("ok-prod" not in t for t in titles)


def test_flags_high_grade_sku_on_nonprod_vm(snapshot_factory, cost_knowledge):
    vms = [_vm("expensive-test", "Standard_M64", env="test")]
    paths = snapshot_factory({"sub-1": {"vms": vms, "app_service_plans": []}})
    ctx = RuleContext.from_snapshot(paths, cost_knowledge)
    findings = list(rule.evaluate(ctx))
    assert len(findings) == 1
    assert findings[0].severity == Severity.MEDIUM
    assert "non-prod" in findings[0].title


def test_flags_basic_asp_on_prod_tag(snapshot_factory, cost_knowledge):
    plans = [
        _asp("basic-prod", "Basic", env="prod"),
        _asp("premium-prod", "PremiumV3", env="prod"),
    ]
    paths = snapshot_factory({"sub-1": {"vms": [], "app_service_plans": plans}})
    ctx = RuleContext.from_snapshot(paths, cost_knowledge)
    findings = list(rule.evaluate(ctx))
    assert len(findings) == 1
    assert "basic-prod" in findings[0].title


def test_flags_premium_asp_on_test_tag(snapshot_factory, cost_knowledge):
    plans = [_asp("premium-test", "PremiumV3", env="test")]
    paths = snapshot_factory({"sub-1": {"vms": [], "app_service_plans": plans}})
    ctx = RuleContext.from_snapshot(paths, cost_knowledge)
    (f,) = list(rule.evaluate(ctx))
    assert "non-prod" in f.title


def test_unrelated_resources_not_flagged(snapshot_factory, cost_knowledge):
    vms = [_vm("untagged", "Standard_D4s_v5")]  # no env tag
    plans = [_asp("untagged", "Basic")]
    paths = snapshot_factory({"sub-1": {"vms": vms, "app_service_plans": plans}})
    ctx = RuleContext.from_snapshot(paths, cost_knowledge)
    assert list(rule.evaluate(ctx)) == []


def test_missing_both_collectors_emits_info(snapshot_factory, cost_knowledge):
    paths = snapshot_factory({"sub-1": {"vms": None, "app_service_plans": None}})
    ctx = RuleContext.from_snapshot(paths, cost_knowledge)
    findings = list(rule.evaluate(ctx))
    assert len(findings) == 1
    assert findings[0].severity == Severity.INFO


def test_knowledge_refs_present(cost_knowledge):
    for ref in rule.KNOWLEDGE_REFS:
        assert cost_knowledge.has(ref)
