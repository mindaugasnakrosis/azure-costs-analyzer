"""Tests for the log_analytics_retention rule."""

from __future__ import annotations

from azure_cost_investigator.rules import log_analytics_retention as rule
from azure_cost_investigator.rules.base import RuleContext
from azure_investigator_core.schema import Severity


def _ws(
    name="ws1",
    *,
    retention: int | None = 31,
    sku: str = "PerGB2018",
    daily_quota_gb: float | None = -1,
    location: str = "uksouth",
) -> dict:
    ws_id = f"/subscriptions/sub-1/resourceGroups/rg/providers/microsoft.operationalinsights/workspaces/{name}"
    return {
        "id": ws_id,
        "name": name,
        "location": location,
        "retentionInDays": retention,
        "sku": {"name": sku},
        "workspaceCapping": {"dailyQuotaGb": daily_quota_gb} if daily_quota_gb is not None else {},
    }


def _consumption_for(ws_id: str, gbp: float) -> dict:
    return {
        "actual": [
            {
                "Cost": gbp,
                "MeterCategory": "Log Analytics",
                "Currency": "GBP",
                "ResourceId": ws_id,
                "UsageDate": 20260401,
                "ServiceName": "Log Analytics",
                "ChargeType": "Usage",
            }
        ]
    }


def test_workspace_within_free_band_is_not_flagged(snapshot_factory, cost_knowledge):
    ws = _ws(retention=31, sku="PerGB2018")
    paths = snapshot_factory({"sub-1": {"log_analytics": [ws]}})
    ctx = RuleContext.from_snapshot(paths, cost_knowledge)
    assert list(rule.evaluate(ctx)) == []


def test_extended_retention_on_current_sku_is_flagged_medium(
    snapshot_factory, cost_knowledge
):
    ws = _ws(retention=180, sku="PerGB2018")
    paths = snapshot_factory({"sub-1": {"log_analytics": [ws]}})
    ctx = RuleContext.from_snapshot(paths, cost_knowledge)
    (f,) = list(rule.evaluate(ctx))
    assert f.severity == Severity.MEDIUM
    assert "180 days" in f.evidence["reason"]
    assert "free band" in f.evidence["reason"]


def test_legacy_sku_alone_is_flagged(snapshot_factory, cost_knowledge):
    ws = _ws(retention=31, sku="Standard")
    paths = snapshot_factory({"sub-1": {"log_analytics": [ws]}})
    ctx = RuleContext.from_snapshot(paths, cost_knowledge)
    (f,) = list(rule.evaluate(ctx))
    assert f.severity == Severity.MEDIUM
    assert "legacy SKU 'standard'" in f.evidence["reason"]


def test_free_sku_emits_info(snapshot_factory, cost_knowledge):
    # The Free SKU is a hard 500MB/day cap, no £ to recover; surface as
    # Info so the user is aware but it doesn't pollute the savings list.
    ws = _ws(retention=31, sku="Free")
    paths = snapshot_factory({"sub-1": {"log_analytics": [ws]}})
    ctx = RuleContext.from_snapshot(paths, cost_knowledge)
    (f,) = list(rule.evaluate(ctx))
    assert f.severity == Severity.INFO


def test_uncapped_with_extended_retention_flags_governance(
    snapshot_factory, cost_knowledge
):
    ws = _ws(retention=730, sku="PerGB2018", daily_quota_gb=-1)
    paths = snapshot_factory({"sub-1": {"log_analytics": [ws]}})
    ctx = RuleContext.from_snapshot(paths, cost_knowledge)
    (f,) = list(rule.evaluate(ctx))
    assert "no daily cap" in f.evidence["reason"]


def test_band_derived_from_consumption_when_present(
    snapshot_factory, cost_knowledge
):
    ws = _ws(retention=730, sku="PerGB2018")
    paths = snapshot_factory(
        {
            "sub-1": {
                "log_analytics": [ws],
                "consumption": _consumption_for(ws["id"], 600.0),
            }
        }
    )
    ctx = RuleContext.from_snapshot(paths, cost_knowledge)
    (f,) = list(rule.evaluate(ctx))
    # 600 × 0.20 = 120, 600 × 0.40 = 240.
    assert float(f.estimated_savings.low_gbp_per_month) == 120.0
    assert float(f.estimated_savings.high_gbp_per_month) == 240.0


def test_no_band_when_consumption_does_not_match_workspace(
    snapshot_factory, cost_knowledge
):
    # Consumption row is for a different workspace ID — must not be
    # attributed to this one.
    ws = _ws(retention=730)
    paths = snapshot_factory(
        {
            "sub-1": {
                "log_analytics": [ws],
                "consumption": _consumption_for("/different/workspace", 600.0),
            }
        }
    )
    ctx = RuleContext.from_snapshot(paths, cost_knowledge)
    (f,) = list(rule.evaluate(ctx))
    assert f.estimated_savings is None


def test_capacity_reservation_is_treated_as_current_sku(
    snapshot_factory, cost_knowledge
):
    # CapacityReservation is the commitment tier — current, not legacy.
    ws = _ws(retention=31, sku="CapacityReservation")
    paths = snapshot_factory({"sub-1": {"log_analytics": [ws]}})
    ctx = RuleContext.from_snapshot(paths, cost_knowledge)
    assert list(rule.evaluate(ctx)) == []


def test_missing_collector_emits_info(snapshot_factory, cost_knowledge):
    paths = snapshot_factory({"sub-1": {"log_analytics": None}})
    ctx = RuleContext.from_snapshot(paths, cost_knowledge)
    (f,) = list(rule.evaluate(ctx))
    assert f.severity == Severity.INFO


def test_factors_overridable_via_config(snapshot_factory, cost_knowledge):
    ws = _ws(retention=730)
    paths = snapshot_factory(
        {
            "sub-1": {
                "log_analytics": [ws],
                "consumption": _consumption_for(ws["id"], 1000.0),
            }
        }
    )
    ctx = RuleContext.from_snapshot(paths, cost_knowledge)
    ctx.config["la_retention_low_factor"] = 0.30
    ctx.config["la_retention_high_factor"] = 0.50
    (f,) = list(rule.evaluate(ctx))
    assert float(f.estimated_savings.low_gbp_per_month) == 300.0
    assert float(f.estimated_savings.high_gbp_per_month) == 500.0


def test_knowledge_refs_present(cost_knowledge):
    for ref in rule.KNOWLEDGE_REFS:
        assert cost_knowledge.has(ref)
