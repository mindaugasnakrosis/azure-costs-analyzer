from __future__ import annotations

from azure_cost_investigator.rules import underused_reservations as rule
from azure_cost_investigator.rules.base import RuleContext
from azure_investigator_core.schema import Severity


def _entry(order_id, reservations):
    return {
        "order": {"id": f"/orders/{order_id}", "displayName": order_id},
        "reservations": reservations,
        "error": None,
    }


def _rsv(name, sku, util_pct=None, util_field="utilization", nested=False):
    rec = {
        "id": f"/r/{name}",
        "name": name,
        "sku": {"name": sku},
        "properties": {"skuName": sku, "displayName": name},
    }
    if util_pct is None:
        return rec
    if nested:
        rec[util_field] = {"aggregates": [{"grain": "30days", "value": util_pct}]}
    else:
        rec[util_field] = util_pct
    return rec


def test_flags_low_utilisation_below_threshold(snapshot_factory, cost_knowledge):
    records = [
        _entry(
            "o1",
            [
                _rsv("low", "Standard_D4s_v5", util_pct=42.0),
                _rsv("good", "Standard_D8s_v5", util_pct=92.0),
            ],
        )
    ]
    paths = snapshot_factory({"sub-1": {"reservations": records}})
    ctx = RuleContext.from_snapshot(paths, cost_knowledge)
    findings = list(rule.evaluate(ctx))
    titles = [f.title for f in findings]
    assert any("low" in t for t in titles)
    assert all("good" not in t for t in titles)
    assert all(f.severity == Severity.MEDIUM for f in findings if "low" in f.title)


def test_threshold_overridable_via_config(snapshot_factory, cost_knowledge):
    records = [_entry("o1", [_rsv("middling", "Standard_D2s_v5", util_pct=85.0)])]
    paths = snapshot_factory({"sub-1": {"reservations": records}})
    ctx = RuleContext.from_snapshot(
        paths,
        cost_knowledge,
    )
    ctx.config["reservation_min_utilisation"] = 90.0
    findings = list(rule.evaluate(ctx))
    assert len(findings) == 1
    assert "middling" in findings[0].title


def test_nested_aggregate_shape_is_read(snapshot_factory, cost_knowledge):
    records = [
        _entry(
            "o1",
            [
                _rsv(
                    "nested",
                    "Standard_E4s_v5",
                    util_pct=40.0,
                    util_field="utilization",
                    nested=True,
                ),
            ],
        )
    ]
    paths = snapshot_factory({"sub-1": {"reservations": records}})
    ctx = RuleContext.from_snapshot(paths, cost_knowledge)
    findings = list(rule.evaluate(ctx))
    assert len(findings) == 1
    assert findings[0].evidence["utilisation_pct"] == 40.0


def test_missing_utilisation_emits_info(snapshot_factory, cost_knowledge):
    records = [_entry("o1", [_rsv("unknown", "Standard_F4s_v2")])]
    paths = snapshot_factory({"sub-1": {"reservations": records}})
    ctx = RuleContext.from_snapshot(paths, cost_knowledge)
    (f,) = list(rule.evaluate(ctx))
    assert f.severity == Severity.INFO


def test_missing_collector_emits_info(snapshot_factory, cost_knowledge):
    paths = snapshot_factory({"sub-1": {"reservations": None}})
    ctx = RuleContext.from_snapshot(paths, cost_knowledge)
    findings = list(rule.evaluate(ctx))
    assert len(findings) == 1
    assert findings[0].severity == Severity.INFO


def test_knowledge_refs_present(cost_knowledge):
    for ref in rule.KNOWLEDGE_REFS:
        assert cost_knowledge.has(ref)
