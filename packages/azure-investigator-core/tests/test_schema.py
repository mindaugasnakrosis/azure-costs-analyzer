from __future__ import annotations

from datetime import UTC, datetime
from decimal import Decimal

import pytest
from azure_investigator_core.schema import (
    CollectorResult,
    Confidence,
    Finding,
    Report,
    SavingsRange,
    Severity,
    SnapshotManifest,
    SubscriptionRef,
)
from pydantic import ValidationError


def _finding(**overrides) -> Finding:
    base = dict(
        rule_id="orphaned_disks",
        title="Unattached managed disk",
        subscription_id="sub-1",
        subscription_name="TEST",
        severity=Severity.MEDIUM,
        confidence=Confidence.HIGH,
        knowledge_refs=["disk-orphan-criteria.md"],
        recommended_investigation="Confirm the disk is not a manual backup before deletion.",
    )
    base.update(overrides)
    return Finding(**base)


class TestSavingsRange:
    def test_assumption_required(self):
        with pytest.raises(ValidationError, match="assumption"):
            SavingsRange(
                low_gbp_per_month=Decimal("10"),
                high_gbp_per_month=Decimal("20"),
                assumption="",
            )

    def test_assumption_whitespace_rejected(self):
        with pytest.raises(ValidationError, match="assumption"):
            SavingsRange(
                low_gbp_per_month=Decimal("10"),
                high_gbp_per_month=Decimal("20"),
                assumption="   ",
            )

    def test_low_must_be_le_high(self):
        with pytest.raises(ValidationError, match="<= "):
            SavingsRange(
                low_gbp_per_month=Decimal("50"),
                high_gbp_per_month=Decimal("10"),
                assumption="Assumes the disk is unused.",
            )

    def test_negatives_rejected(self):
        with pytest.raises(ValidationError, match="non-negative"):
            SavingsRange(
                low_gbp_per_month=Decimal("-1"),
                high_gbp_per_month=Decimal("10"),
                assumption="Assumes the disk is unused.",
            )

    def test_valid(self):
        s = SavingsRange(
            low_gbp_per_month=Decimal("8.50"),
            high_gbp_per_month=Decimal("12.00"),
            assumption="Assumes the disk is genuinely orphaned.",
        )
        assert s.low_gbp_per_month == Decimal("8.50")


class TestFinding:
    def test_subscription_id_required(self):
        with pytest.raises(ValidationError):
            _finding(subscription_id="")

    def test_recommended_investigation_required(self):
        with pytest.raises(ValidationError, match="recommended_investigation"):
            _finding(recommended_investigation="   ")

    def test_non_info_must_cite_knowledge(self):
        with pytest.raises(ValidationError, match="knowledge_refs"):
            _finding(severity=Severity.HIGH, knowledge_refs=[])

    def test_info_may_skip_knowledge(self):
        f = _finding(severity=Severity.INFO, knowledge_refs=[])
        assert f.severity == Severity.INFO

    def test_savings_assumption_propagates(self):
        f = _finding(
            estimated_savings=SavingsRange(
                low_gbp_per_month=Decimal("5"),
                high_gbp_per_month=Decimal("9"),
                assumption="Assumes 30 days of zero attach.",
            )
        )
        assert f.estimated_savings.assumption.startswith("Assumes")


class TestReport:
    def test_total_savings_sums_ranges(self):
        f1 = _finding(
            rule_id="r1",
            estimated_savings=SavingsRange(
                low_gbp_per_month=Decimal("10"),
                high_gbp_per_month=Decimal("15"),
                assumption="x",
            ),
        )
        f2 = _finding(
            rule_id="r2",
            estimated_savings=SavingsRange(
                low_gbp_per_month=Decimal("4.25"),
                high_gbp_per_month=Decimal("6.75"),
                assumption="y",
            ),
        )
        f3 = _finding(rule_id="r3", severity=Severity.INFO, knowledge_refs=[])
        r = Report(
            snapshot_id="2026-04-29T10-00-00",
            generated_at=datetime.now(UTC),
            findings=[f1, f2, f3],
        )
        low, high = r.total_savings_range_gbp_per_month()
        assert low == Decimal("14.25")
        assert high == Decimal("21.75")

    def test_by_severity_filter(self):
        crit = _finding(rule_id="c", severity=Severity.CRITICAL)
        med = _finding(rule_id="m", severity=Severity.MEDIUM)
        r = Report(
            snapshot_id="s",
            generated_at=datetime.now(UTC),
            findings=[crit, med],
        )
        assert r.by_severity(Severity.CRITICAL) == [crit]


class TestSnapshotManifest:
    def test_collectors_for_filters_to_subscription_and_ok(self):
        now = datetime.now(UTC)
        m = SnapshotManifest(
            snapshot_id="s1",
            started_at=now,
            identity="me@example.com",
            subscriptions=[SubscriptionRef(id="sub-1", name="TEST")],
            collectors_run=["vms", "disks"],
            collector_results=[
                CollectorResult(
                    collector="vms",
                    subscription_id="sub-1",
                    status="ok",
                    started_at=now,
                    finished_at=now,
                ),
                CollectorResult(
                    collector="disks",
                    subscription_id="sub-1",
                    status="error",
                    error="auth failed",
                    started_at=now,
                    finished_at=now,
                ),
                CollectorResult(
                    collector="vms",
                    subscription_id="sub-2",
                    status="ok",
                    started_at=now,
                    finished_at=now,
                ),
            ],
        )
        assert m.collectors_for("sub-1") == {"vms"}
        assert m.has_data("sub-1", "vms") is True
        assert m.has_data("sub-1", "disks") is False
