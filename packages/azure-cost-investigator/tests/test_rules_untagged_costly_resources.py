from __future__ import annotations

from azure_cost_investigator.rules import untagged_costly_resources as rule
from azure_cost_investigator.rules.base import RuleContext
from azure_investigator_core.schema import Severity


def _vm(name, tags=None):
    return {"id": f"/sub/vms/{name}", "name": name, "location": "uksouth", "tags": tags or {}}


def _asp(name, tags=None):
    return {
        "id": f"/sub/asps/{name}",
        "name": name,
        "location": "uksouth",
        "sku": {"tier": "Basic", "name": "B1"},
        "numberOfSites": 1,
        "tags": tags or {},
    }


def test_flags_resources_missing_accounting_tag(snapshot_factory, cost_knowledge):
    vms = [
        _vm("compliant", tags={"costcenter": "55", "env": "prod"}),
        _vm("missing-cc", tags={"env": "prod"}),
    ]
    paths = snapshot_factory({"sub-1": {"vms": vms}})
    ctx = RuleContext.from_snapshot(paths, cost_knowledge)
    findings = list(rule.evaluate(ctx))
    assert len(findings) == 1
    f = findings[0]
    assert "missing-cc" in f.title
    assert "accounting" in f.evidence["missing_tag_categories"]
    assert f.severity == Severity.LOW


def test_flags_resources_missing_env_tag(snapshot_factory, cost_knowledge):
    vms = [_vm("missing-env", tags={"costcenter": "55"})]
    paths = snapshot_factory({"sub-1": {"vms": vms}})
    ctx = RuleContext.from_snapshot(paths, cost_knowledge)
    (f,) = list(rule.evaluate(ctx))
    assert "functional/env" in f.evidence["missing_tag_categories"]


def test_flags_completely_untagged_resources(snapshot_factory, cost_knowledge):
    plans = [_asp("naked")]
    paths = snapshot_factory({"sub-1": {"app_service_plans": plans}})
    ctx = RuleContext.from_snapshot(paths, cost_knowledge)
    (f,) = list(rule.evaluate(ctx))
    assert set(f.evidence["missing_tag_categories"]) == {"accounting", "functional/env"}


def test_recognises_alternative_accounting_tag_keys(snapshot_factory, cost_knowledge):
    vms = [
        _vm("dept", tags={"department": "Eng", "env": "prod"}),
        _vm("bu", tags={"businessunit": "finance", "env": "prod"}),
        _vm("budget", tags={"budget": "200000", "env": "prod"}),
    ]
    paths = snapshot_factory({"sub-1": {"vms": vms}})
    ctx = RuleContext.from_snapshot(paths, cost_knowledge)
    assert list(rule.evaluate(ctx)) == []


def test_missing_all_collectors_emits_info(snapshot_factory, cost_knowledge):
    paths = snapshot_factory(
        {
            "sub-1": {
                "vms": None,
                "app_service_plans": None,
                "storage_accounts": None,
                "sql": None,
            }
        }
    )
    ctx = RuleContext.from_snapshot(paths, cost_knowledge)
    findings = list(rule.evaluate(ctx))
    assert len(findings) == 1
    assert findings[0].severity == Severity.INFO


def test_knowledge_refs_present(cost_knowledge):
    for ref in rule.KNOWLEDGE_REFS:
        assert cost_knowledge.has(ref)
