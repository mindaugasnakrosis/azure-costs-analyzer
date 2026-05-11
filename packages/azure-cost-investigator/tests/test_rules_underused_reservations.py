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


def test_utilisation_error_surfaces_in_recommendation(snapshot_factory, cost_knowledge):
    rsv = _rsv("blocked", "Standard_D4s_v5")
    rsv["_utilisation_error"] = (
        "(AuthorizationFailed) caller lacks Reservations Reader on the order"
    )
    records = [_entry("o1", [rsv])]
    paths = snapshot_factory({"sub-1": {"reservations": records}})
    ctx = RuleContext.from_snapshot(paths, cost_knowledge)
    (f,) = list(rule.evaluate(ctx))
    assert f.severity == Severity.INFO
    assert f.evidence["reason"] == "consumption summary call failed"
    assert "AuthorizationFailed" in f.recommended_investigation


def test_missing_collector_emits_info(snapshot_factory, cost_knowledge):
    paths = snapshot_factory({"sub-1": {"reservations": None}})
    ctx = RuleContext.from_snapshot(paths, cost_knowledge)
    findings = list(rule.evaluate(ctx))
    assert len(findings) == 1
    assert findings[0].severity == Severity.INFO


def test_knowledge_refs_present(cost_knowledge):
    for ref in rule.KNOWLEDGE_REFS:
        assert cost_knowledge.has(ref)


def test_zero_util_vm_ri_gets_savings_band(snapshot_factory, cost_knowledge):
    # Zero-utilisation VM RI: full waste fraction, ~60% retail factor.
    # Standard_D family bands are (40, 90); for quantity=1 expect roughly
    # low ≈ 40 × 0.60 × 1.0 = 24, high ≈ 90 × 0.60 × 1.0 = 54.
    rsv = _rsv("dead", "Standard_D4s_v5", util_pct=0.0)
    rsv["properties"]["quantity"] = 1
    paths = snapshot_factory({"sub-1": {"reservations": [_entry("o1", [rsv])]}})
    ctx = RuleContext.from_snapshot(paths, cost_knowledge)
    (f,) = list(rule.evaluate(ctx))
    assert f.estimated_savings is not None
    assert float(f.estimated_savings.low_gbp_per_month) == 24.0
    assert float(f.estimated_savings.high_gbp_per_month) == 54.0
    assert f.evidence["quantity"] == 1


def test_partial_util_scales_band_by_waste_fraction(snapshot_factory, cost_knowledge):
    # 50% util on Standard_D4s_v5, qty=2 → waste=0.5, qty multiplier=2:
    # low = 40 × 0.60 × 0.5 × 2 = 24, high = 90 × 0.60 × 0.5 × 2 = 54.
    rsv = _rsv("half", "Standard_D4s_v5", util_pct=50.0)
    rsv["properties"]["quantity"] = 2
    paths = snapshot_factory({"sub-1": {"reservations": [_entry("o1", [rsv])]}})
    ctx = RuleContext.from_snapshot(paths, cost_knowledge)
    (f,) = list(rule.evaluate(ctx))
    assert float(f.estimated_savings.low_gbp_per_month) == 24.0
    assert float(f.estimated_savings.high_gbp_per_month) == 54.0


def test_non_vm_reservation_has_no_band(snapshot_factory, cost_knowledge):
    # SQL DTU / Cosmos / Synapse SKUs don't start with "Standard_" or
    # "Basic_"; we cannot price them from the family bands. The finding
    # must still surface so triage sees the under-utilised reservation.
    rsv = _rsv("sql", "SQLDB_S0", util_pct=10.0)
    paths = snapshot_factory({"sub-1": {"reservations": [_entry("o1", [rsv])]}})
    ctx = RuleContext.from_snapshot(paths, cost_knowledge)
    (f,) = list(rule.evaluate(ctx))
    assert f.estimated_savings is None
    assert f.severity == Severity.MEDIUM


def test_ri_factor_overridable_via_config(snapshot_factory, cost_knowledge):
    # Override 0.60 → 1.00 (treat reservation cost as full retail) — band
    # should scale proportionally.
    rsv = _rsv("dead", "Standard_D4s_v5", util_pct=0.0)
    rsv["properties"]["quantity"] = 1
    paths = snapshot_factory({"sub-1": {"reservations": [_entry("o1", [rsv])]}})
    ctx = RuleContext.from_snapshot(paths, cost_knowledge)
    ctx.config["reservation_ri_retail_factor"] = 1.0
    (f,) = list(rule.evaluate(ctx))
    # low = 40 × 1.0 × 1.0 × 1 = 40, high = 90 × 1.0 × 1.0 × 1 = 90.
    assert float(f.estimated_savings.low_gbp_per_month) == 40.0
    assert float(f.estimated_savings.high_gbp_per_month) == 90.0


def test_app_service_reservation_gets_band(snapshot_factory, cost_knowledge):
    # P2v3 Linux × 5 at 40% util → waste 0.6 × 280-340 × 0.6 × 5 = 504-612.
    rsv = _rsv(
        "asp", "azure_app_service_premium_v3_plan_linux_p2_v3", util_pct=40.0
    )
    rsv["properties"]["quantity"] = 5
    paths = snapshot_factory({"sub-1": {"reservations": [_entry("o1", [rsv])]}})
    ctx = RuleContext.from_snapshot(paths, cost_knowledge)
    (f,) = list(rule.evaluate(ctx))
    assert f.estimated_savings is not None
    # 280 × 0.6 × 0.6 × 5 = 504, 340 × 0.6 × 0.6 × 5 = 612.
    assert float(f.estimated_savings.low_gbp_per_month) == 504.0
    assert float(f.estimated_savings.high_gbp_per_month) == 612.0


def test_premium_disk_reservation_gets_band(snapshot_factory, cost_knowledge):
    # P30 × 4 at 25% util → waste 0.75 × 100-135 × 0.6 × 4 = 180-243.
    rsv = _rsv("disk", "Premium_SSD_Managed_Disks_P30", util_pct=25.0)
    rsv["properties"]["quantity"] = 4
    paths = snapshot_factory({"sub-1": {"reservations": [_entry("o1", [rsv])]}})
    ctx = RuleContext.from_snapshot(paths, cost_knowledge)
    (f,) = list(rule.evaluate(ctx))
    assert f.estimated_savings is not None
    # 100 × 0.6 × 0.75 × 4 = 180, 135 × 0.6 × 0.75 × 4 = 243.
    assert float(f.estimated_savings.low_gbp_per_month) == 180.0
    assert float(f.estimated_savings.high_gbp_per_month) == 243.0


def test_forecast_uses_default_horizon_when_no_expiry(snapshot_factory, cost_knowledge):
    rsv = _rsv("dead", "Standard_D4s_v5", util_pct=0.0)
    rsv["properties"]["quantity"] = 1
    paths = snapshot_factory({"sub-1": {"reservations": [_entry("o1", [rsv])]}})
    ctx = RuleContext.from_snapshot(paths, cost_knowledge)
    (f,) = list(rule.evaluate(ctx))
    assert f.evidence["term_remaining_months"] == 12
    assert "default" in f.evidence["term_source"]
    # 100% waste, factor 0.6, qty 1, D-family band (40, 90)
    # monthly: 24-54; forecast: 24×12=288 to 54×12=648
    assert f.evidence["forecast_low_gbp_to_expiry"] == 288.0
    assert f.evidence["forecast_high_gbp_to_expiry"] == 648.0


def test_forecast_horizon_overridable(snapshot_factory, cost_knowledge):
    rsv = _rsv("dead", "Standard_D4s_v5", util_pct=0.0)
    rsv["properties"]["quantity"] = 1
    paths = snapshot_factory({"sub-1": {"reservations": [_entry("o1", [rsv])]}})
    ctx = RuleContext.from_snapshot(paths, cost_knowledge)
    ctx.config["reservation_forecast_months"] = 36
    (f,) = list(rule.evaluate(ctx))
    assert f.evidence["term_remaining_months"] == 36
    assert f.evidence["forecast_low_gbp_to_expiry"] == 24.0 * 36
    assert f.evidence["forecast_high_gbp_to_expiry"] == 54.0 * 36


def test_forecast_uses_expiry_when_present(snapshot_factory, cost_knowledge):
    from datetime import (  # noqa: PLC0415  # local to keep cold-test import cost off the suite
        UTC,
        datetime,
        timedelta,
    )

    expiry = (datetime.now(UTC) + timedelta(days=180)).isoformat()
    rsv = _rsv("dead", "Standard_D4s_v5", util_pct=0.0)
    rsv["properties"]["quantity"] = 1
    rsv["properties"]["expiryDateTime"] = expiry
    paths = snapshot_factory({"sub-1": {"reservations": [_entry("o1", [rsv])]}})
    ctx = RuleContext.from_snapshot(paths, cost_knowledge)
    (f,) = list(rule.evaluate(ctx))
    # 180 days ≈ 6 months
    assert 5 <= f.evidence["term_remaining_months"] <= 7
    assert "expiryDateTime" in f.evidence["term_source"]


def test_quantity_falls_back_to_one_when_missing(snapshot_factory, cost_knowledge):
    # Older payload shapes don't carry `quantity` — default to 1 reservation.
    rsv = _rsv("dead", "Standard_D4s_v5", util_pct=0.0)
    # Note: properties has no quantity key.
    paths = snapshot_factory({"sub-1": {"reservations": [_entry("o1", [rsv])]}})
    ctx = RuleContext.from_snapshot(paths, cost_knowledge)
    (f,) = list(rule.evaluate(ctx))
    assert f.evidence["quantity"] == 1
    assert f.estimated_savings is not None
