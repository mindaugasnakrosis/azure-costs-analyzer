from __future__ import annotations

from azure_cost_investigator.rules import unused_app_service_plans as rule
from azure_cost_investigator.rules.base import RuleContext
from azure_investigator_core.schema import Confidence, Severity

PLANS = [
    {
        "id": "/sub/asps/empty-basic",
        "name": "empty-basic",
        "location": "uksouth",
        "sku": {"tier": "Basic", "name": "B1"},
        "numberOfSites": 0,
        "numberOfWorkers": 1,
    },
    {
        "id": "/sub/asps/used-premium",
        "name": "used-premium",
        "location": "uksouth",
        "sku": {"tier": "PremiumV3", "name": "P2v3"},
        "numberOfSites": 5,
        "numberOfWorkers": 1,
    },
    {
        "id": "/sub/asps/empty-shared",
        "name": "empty-shared",
        "location": "uksouth",
        "sku": {"tier": "Shared", "name": "D1"},
        "numberOfSites": 0,
        "numberOfWorkers": 1,
    },
    {
        "id": "/sub/asps/empty-premium-2workers",
        "name": "empty-premium-2workers",
        "location": "uksouth",
        "sku": {"tier": "PremiumV3", "name": "P3v3"},
        "numberOfSites": 0,
        "numberOfWorkers": 2,
    },
]


def test_flags_only_dedicated_empty_plans(snapshot_factory, cost_knowledge):
    paths = snapshot_factory({"sub-1": {"app_service_plans": PLANS}})
    ctx = RuleContext.from_snapshot(paths, cost_knowledge)
    findings = list(rule.evaluate(ctx))
    titles = {f.title for f in findings}
    assert any("empty-basic" in t for t in titles)
    assert any("empty-premium-2workers" in t for t in titles)
    assert all("used-premium" not in t for t in titles)
    assert all("empty-shared" not in t for t in titles)
    assert len(findings) == 2


def test_savings_scales_with_workers(snapshot_factory, cost_knowledge):
    paths = snapshot_factory({"sub-1": {"app_service_plans": [PLANS[3]]}})
    ctx = RuleContext.from_snapshot(paths, cost_knowledge)
    (f,) = list(rule.evaluate(ctx))
    # PremiumV3 band is (90, 600); 2 workers → (180, 1200)
    assert float(f.estimated_savings.low_gbp_per_month) == 180.0
    assert float(f.estimated_savings.high_gbp_per_month) == 1200.0
    assert f.severity == Severity.HIGH
    assert f.confidence == Confidence.HIGH


def test_missing_collector_emits_info(snapshot_factory, cost_knowledge):
    paths = snapshot_factory({"sub-1": {"app_service_plans": None}})
    ctx = RuleContext.from_snapshot(paths, cost_knowledge)
    findings = list(rule.evaluate(ctx))
    assert len(findings) == 1
    assert findings[0].severity == Severity.INFO


def test_knowledge_refs_present(cost_knowledge):
    for ref in rule.KNOWLEDGE_REFS:
        assert cost_knowledge.has(ref)
