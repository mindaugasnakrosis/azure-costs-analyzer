"""Tests for the analyse-layer severity re-tier by £/mo savings band.

The re-tier replaces each rule's hardcoded severity with one derived from
the high end of the savings band. Calibrated for a £30k/mo tenant —
overridable via config.
"""

from __future__ import annotations

from decimal import Decimal

from azure_cost_investigator.analyse import _retier_by_cost
from azure_investigator_core.schema import Confidence, Finding, SavingsRange, Severity


def _f(**overrides) -> Finding:
    base = dict(
        rule_id="orphaned_disks",
        title="x",
        subscription_id="sub-1",
        subscription_name="TEST",
        severity=Severity.MEDIUM,
        confidence=Confidence.HIGH,
        knowledge_refs=["disk-orphan-criteria.md"],
        recommended_investigation="confirm",
    )
    base.update(overrides)
    return Finding(**base)


def _band(low, high):
    return SavingsRange(
        low_gbp_per_month=Decimal(str(low)),
        high_gbp_per_month=Decimal(str(high)),
        assumption="t",
    )


THRESHOLDS = (
    (Severity.CRITICAL, Decimal("1500")),
    (Severity.HIGH, Decimal("200")),
    (Severity.MEDIUM, Decimal("30")),
    (Severity.LOW, Decimal("0")),
)


def test_high_band_promotes_idle_vm_from_medium_to_high():
    f = _f(severity=Severity.MEDIUM, estimated_savings=_band(60, 130))
    (out,) = _retier_by_cost([f], THRESHOLDS)
    assert out.severity == Severity.LOW or out.severity == Severity.MEDIUM
    # 130 is just below the 200 threshold for High; correct band is Medium.
    assert out.severity == Severity.MEDIUM


def test_high_band_at_200_qualifies_for_high():
    f = _f(severity=Severity.MEDIUM, estimated_savings=_band(50, 200))
    (out,) = _retier_by_cost([f], THRESHOLDS)
    assert out.severity == Severity.HIGH


def test_band_above_1500_becomes_critical():
    f = _f(severity=Severity.HIGH, estimated_savings=_band(900, 2000))
    (out,) = _retier_by_cost([f], THRESHOLDS)
    assert out.severity == Severity.CRITICAL


def test_high_authored_finding_demotes_to_low_when_band_is_tiny():
    # A £3/mo orphan IP currently surfaces as Medium by rule; re-tier should
    # demote it to Low so triage isn't drowned in £-trivial Mediums.
    f = _f(severity=Severity.MEDIUM, estimated_savings=_band(2, 3))
    (out,) = _retier_by_cost([f], THRESHOLDS)
    assert out.severity == Severity.LOW


def test_info_severity_is_never_re_tiered():
    f = _f(severity=Severity.INFO, knowledge_refs=[])
    (out,) = _retier_by_cost([f], THRESHOLDS)
    assert out.severity == Severity.INFO


def test_governance_finding_with_no_band_keeps_rule_severity():
    # Tagging / env-mismatch findings have no estimated_savings; their
    # severity is the rule's editorial choice, not a £ judgement.
    f = _f(severity=Severity.MEDIUM, estimated_savings=None)
    (out,) = _retier_by_cost([f], THRESHOLDS)
    assert out.severity == Severity.MEDIUM


def test_thresholds_overridable_for_smaller_tenants():
    # A startup running £1k/mo on Azure shouldn't see Critical at £1500/mo;
    # a custom threshold table re-anchors triage to their scale.
    custom = (
        (Severity.CRITICAL, Decimal("100")),
        (Severity.HIGH, Decimal("20")),
        (Severity.MEDIUM, Decimal("5")),
        (Severity.LOW, Decimal("0")),
    )
    f = _f(severity=Severity.MEDIUM, estimated_savings=_band(50, 130))
    (out,) = _retier_by_cost([f], custom)
    assert out.severity == Severity.CRITICAL
