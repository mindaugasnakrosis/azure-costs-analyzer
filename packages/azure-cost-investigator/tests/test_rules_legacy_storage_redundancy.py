from __future__ import annotations

from azure_cost_investigator.rules import legacy_storage_redundancy as rule
from azure_cost_investigator.rules.base import RuleContext
from azure_investigator_core.schema import Severity


def _acc(name, sku, env=None, access_tier="Hot"):
    return {
        "id": f"/sub/sa/{name}",
        "name": name,
        "location": "uksouth",
        "sku": {"name": sku},
        "accessTier": access_tier,
        "tags": {"env": env} if env else {},
    }


def test_flags_grs_and_ragrs_only(snapshot_factory, cost_knowledge):
    accs = [
        _acc("grs", "Standard_GRS"),
        _acc("ragrs", "Standard_RAGRS"),
        _acc("lrs", "Standard_LRS"),
        _acc("zrs", "Standard_ZRS"),
        _acc("gzrs", "Standard_GZRS"),
    ]
    paths = snapshot_factory({"sub-1": {"storage_accounts": accs}})
    ctx = RuleContext.from_snapshot(paths, cost_knowledge)
    findings = list(rule.evaluate(ctx))
    flagged = sorted(f.evidence["sku"] for f in findings)
    assert flagged == ["Standard_GRS", "Standard_GZRS", "Standard_RAGRS"]


def test_severity_bumps_to_medium_when_env_is_nonprod(snapshot_factory, cost_knowledge):
    accs = [
        _acc("nonprod-grs", "Standard_GRS", env="test"),
        _acc("plain-grs", "Standard_GRS"),
    ]
    paths = snapshot_factory({"sub-1": {"storage_accounts": accs}})
    ctx = RuleContext.from_snapshot(paths, cost_knowledge)
    by_name = {f.resource_name: f for f in rule.evaluate(ctx)}
    assert by_name["nonprod-grs"].severity == Severity.MEDIUM
    assert by_name["plain-grs"].severity == Severity.LOW


def test_missing_collector_emits_info(snapshot_factory, cost_knowledge):
    paths = snapshot_factory({"sub-1": {"storage_accounts": None}})
    ctx = RuleContext.from_snapshot(paths, cost_knowledge)
    findings = list(rule.evaluate(ctx))
    assert len(findings) == 1
    assert findings[0].severity == Severity.INFO


def test_knowledge_refs_present(cost_knowledge):
    for ref in rule.KNOWLEDGE_REFS:
        assert cost_knowledge.has(ref)
