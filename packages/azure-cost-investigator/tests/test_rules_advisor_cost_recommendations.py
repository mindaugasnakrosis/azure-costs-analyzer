from __future__ import annotations

from azure_cost_investigator.rules import advisor_cost_recommendations as rule
from azure_cost_investigator.rules.base import RuleContext
from azure_investigator_core.schema import Confidence, Severity


def _rec(*, problem, impact, annual_savings=None, currency="USD", sku=None, sub_cat=None):
    ep = {}
    if annual_savings is not None:
        ep["annualSavingsAmount"] = annual_savings
        ep["savingsCurrency"] = currency
    if sku:
        ep["sku"] = sku
    if sub_cat:
        ep["recommendationSubCategory"] = sub_cat
    return {
        "category": "Cost",
        "impact": impact,
        "shortDescription": {"problem": problem, "solution": problem},
        "extendedProperties": ep,
        "id": f"/r/{problem}",
        "name": problem,
        "recommendationTypeId": "test-type",
    }


def test_high_impact_advisor_passes_through_to_severity_high(snapshot_factory, cost_knowledge):
    rec = _rec(
        problem="Consider VM reserved instance",
        impact="High",
        annual_savings="7186",
        sku="Standard_D4ds_v5",
        sub_cat="Reservations",
    )
    paths = snapshot_factory({"sub-1": {"advisor": [rec]}})
    ctx = RuleContext.from_snapshot(paths, cost_knowledge)
    (f,) = list(rule.evaluate(ctx))
    assert f.severity == Severity.HIGH
    assert f.confidence == Confidence.HIGH
    # ~7186 USD/yr * 0.79 / 12 ≈ £473/mo, ±10% band.
    assert f.estimated_savings is not None
    assert 380 < float(f.estimated_savings.low_gbp_per_month) < 500
    assert 450 < float(f.estimated_savings.high_gbp_per_month) < 550
    assert "Microsoft Advisor estimate" in f.estimated_savings.assumption


def test_savings_currency_other_than_usd_or_gbp_skips_band(snapshot_factory, cost_knowledge):
    rec = _rec(
        problem="Consider X",
        impact="Medium",
        annual_savings="1000",
        currency="EUR",
        sub_cat="Reservations",
    )
    paths = snapshot_factory({"sub-1": {"advisor": [rec]}})
    ctx = RuleContext.from_snapshot(paths, cost_knowledge)
    (f,) = list(rule.evaluate(ctx))
    # The recommendation still surfaces but without a savings band.
    assert f.estimated_savings is None


def test_unquantified_recommendation_still_surfaces(snapshot_factory, cost_knowledge):
    rec = _rec(
        problem="Switch to Prometheus-based Container Insights",
        impact="Medium",
        annual_savings=None,
        sub_cat="MonitoringAndAlerting",
    )
    paths = snapshot_factory({"sub-1": {"advisor": [rec]}})
    ctx = RuleContext.from_snapshot(paths, cost_knowledge)
    (f,) = list(rule.evaluate(ctx))
    assert f.severity == Severity.MEDIUM
    assert f.estimated_savings is None
    assert "Prometheus" in f.title


def test_non_cost_advisor_recommendations_are_ignored(snapshot_factory, cost_knowledge):
    paths = snapshot_factory(
        {
            "sub-1": {
                "advisor": [
                    {"category": "Performance", "impact": "High", "shortDescription": {"problem": "x"}},
                    {"category": "Security", "impact": "High", "shortDescription": {"problem": "y"}},
                ]
            }
        }
    )
    ctx = RuleContext.from_snapshot(paths, cost_knowledge)
    assert list(rule.evaluate(ctx)) == []


def test_missing_advisor_collector_emits_no_findings(snapshot_factory, cost_knowledge):
    paths = snapshot_factory({"sub-1": {"advisor": None}})
    ctx = RuleContext.from_snapshot(paths, cost_knowledge)
    assert list(rule.evaluate(ctx)) == []


def test_fx_rate_overridable_via_config(snapshot_factory, cost_knowledge):
    rec = _rec(
        problem="Consider VM RI",
        impact="High",
        annual_savings="12000",
        sub_cat="Reservations",
    )
    paths = snapshot_factory({"sub-1": {"advisor": [rec]}})
    ctx = RuleContext.from_snapshot(paths, cost_knowledge)
    ctx.config["fx_usd_gbp"] = 1.0  # treat USD as GBP for the test
    (f,) = list(rule.evaluate(ctx))
    # 12000/12 = 1000/mo, ±10% → [900, 1100]
    assert float(f.estimated_savings.low_gbp_per_month) == 900.0
    assert float(f.estimated_savings.high_gbp_per_month) == 1100.0
