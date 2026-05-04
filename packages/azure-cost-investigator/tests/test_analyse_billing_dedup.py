"""Tests for the billing-scope dedup pass.

Reservations are a billing-account-scope resource, so the reservations
collector returns the same orders for every subscription it runs against.
This pass keeps one finding per (rule, reservation_id) so the headline
isn't inflated by N subscriptions surfacing the same waste.
"""

from __future__ import annotations

from decimal import Decimal

from azure_cost_investigator.analyse import _dedup_billing_scope_findings
from azure_investigator_core.schema import Confidence, Finding, SavingsRange, Severity


def _rsv_finding(
    *,
    rsv_id: str,
    sub_id: str,
    sub_name: str,
    high: int | None = 100,
) -> Finding:
    band = None
    if high is not None:
        band = SavingsRange(
            low_gbp_per_month=Decimal("10"),
            high_gbp_per_month=Decimal(str(high)),
            assumption="t",
        )
    return Finding(
        rule_id="underused_reservations",
        title=f"Underused reservation: {rsv_id}",
        subscription_id=sub_id,
        subscription_name=sub_name,
        severity=Severity.MEDIUM,
        confidence=Confidence.MEDIUM,
        knowledge_refs=["reservations-utilisation.md"],
        resource_id=f"/r/{rsv_id}",
        resource_name=rsv_id,
        estimated_savings=band,
        recommended_investigation="x",
    )


def test_same_reservation_in_two_subs_is_kept_once():
    a = _rsv_finding(rsv_id="abc", sub_id="sub-1", sub_name="TEST")
    b = _rsv_finding(rsv_id="abc", sub_id="sub-2", sub_name="PROD")
    out = _dedup_billing_scope_findings([a, b])
    assert len(out) == 1
    assert out[0].resource_id == "/r/abc"


def test_different_reservations_are_both_kept():
    a = _rsv_finding(rsv_id="abc", sub_id="sub-1", sub_name="TEST")
    b = _rsv_finding(rsv_id="xyz", sub_id="sub-1", sub_name="TEST")
    out = _dedup_billing_scope_findings([a, b])
    assert {f.resource_id for f in out} == {"/r/abc", "/r/xyz"}


def test_winner_is_the_finding_with_highest_band():
    # When two subs surface the same reservation but with slightly different
    # bands (e.g. one collector run hit a transient API hiccup), keep the
    # one with the most information — highest high-end of the band.
    weak = _rsv_finding(rsv_id="abc", sub_id="sub-1", sub_name="TEST", high=50)
    strong = _rsv_finding(rsv_id="abc", sub_id="sub-2", sub_name="PROD", high=120)
    (kept,) = _dedup_billing_scope_findings([weak, strong])
    assert kept.subscription_name == "PROD"
    assert kept.estimated_savings.high_gbp_per_month == Decimal("120")


def test_kept_finding_lists_other_subs_in_recommendation():
    a = _rsv_finding(rsv_id="abc", sub_id="sub-1", sub_name="TEST", high=120)
    b = _rsv_finding(rsv_id="abc", sub_id="sub-2", sub_name="PROD", high=60)
    (kept,) = _dedup_billing_scope_findings([a, b])
    assert "Also surfaced in: PROD" in kept.recommended_investigation
    assert "billing-account-scope" in kept.recommended_investigation


def test_finding_with_no_band_loses_to_finding_with_band():
    # An info-poor record (no band) shouldn't beat a record that does have
    # a savings estimate — pick the band-bearing one so the headline is
    # populated.
    none_band = _rsv_finding(rsv_id="abc", sub_id="sub-1", sub_name="TEST", high=None)
    with_band = _rsv_finding(rsv_id="abc", sub_id="sub-2", sub_name="PROD", high=60)
    (kept,) = _dedup_billing_scope_findings([none_band, with_band])
    assert kept.estimated_savings is not None
    assert kept.subscription_name == "PROD"


def test_non_billing_scope_rules_are_passed_through():
    # idle_vms is subscription-scope; the dedup pass must not touch it
    # even when the same resource id (in theory) appears in multiple subs.
    f = Finding(
        rule_id="idle_vms",
        title="x",
        subscription_id="sub-1",
        subscription_name="TEST",
        severity=Severity.MEDIUM,
        confidence=Confidence.MEDIUM,
        knowledge_refs=["vm-rightsizing-thresholds.md"],
        resource_id="/vm/A",
        resource_name="A",
        recommended_investigation="x",
    )
    g = Finding(
        rule_id="idle_vms",
        title="x",
        subscription_id="sub-2",
        subscription_name="PROD",
        severity=Severity.MEDIUM,
        confidence=Confidence.MEDIUM,
        knowledge_refs=["vm-rightsizing-thresholds.md"],
        resource_id="/vm/A",
        resource_name="A",
        recommended_investigation="x",
    )
    out = _dedup_billing_scope_findings([f, g])
    assert len(out) == 2


def test_single_occurrence_does_not_get_an_annotation():
    # A reservation that surfaces in only one subscription run shouldn't
    # have a noisy "Also surfaced in: ..." note appended.
    a = _rsv_finding(rsv_id="abc", sub_id="sub-1", sub_name="TEST")
    (kept,) = _dedup_billing_scope_findings([a])
    assert "Also surfaced in" not in kept.recommended_investigation


def test_input_order_preserved_for_kept_findings():
    # Stable ordering: the kept finding stays in its original input position
    # so report sections render predictably.
    other = _rsv_finding(rsv_id="other", sub_id="sub-1", sub_name="TEST")
    a = _rsv_finding(rsv_id="abc", sub_id="sub-1", sub_name="TEST", high=120)
    b = _rsv_finding(rsv_id="abc", sub_id="sub-2", sub_name="PROD", high=60)
    out = _dedup_billing_scope_findings([other, a, b])
    assert [f.resource_id for f in out] == ["/r/other", "/r/abc"]
