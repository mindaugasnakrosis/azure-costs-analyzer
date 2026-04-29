from __future__ import annotations

from datetime import UTC, datetime
from decimal import Decimal

import pytest
import yaml
from azure_cost_investigator import analyse
from azure_cost_investigator import report as report_mod
from azure_investigator_core.knowledge_loader import KnowledgeCorpus
from azure_investigator_core.schema import (
    Confidence,
    Finding,
    Report,
    SavingsRange,
    Severity,
)


def _finding(**overrides) -> Finding:
    base = dict(
        rule_id="orphaned_disks",
        title="Orphaned managed disk: x",
        subscription_id="sub-1",
        subscription_name="TEST",
        severity=Severity.MEDIUM,
        confidence=Confidence.HIGH,
        knowledge_refs=["disk-orphan-criteria.md"],
        recommended_investigation="confirm not a backup",
    )
    base.update(overrides)
    return Finding(**base)


def _report(findings, currency="GBP") -> Report:
    return Report(
        snapshot_id="2026-04-29T10-00-00Z",
        generated_at=datetime(2026, 4, 29, 10, 0, tzinfo=UTC),
        currency=currency,
        findings=findings,
    )


# ---- analyse_snapshot --------------------------------------------------------


def test_analyse_runs_all_rules_against_real_snapshot(snapshot_factory, cost_knowledge):
    paths = snapshot_factory(
        {
            "sub-1": {
                "vms": [],
                "disks": [],
                "public_ips": [],
                "app_service_plans": [],
                "snapshots": [],
                "vm_metrics": [],
                "reservations": [],
                "storage_accounts": [],
                "sql": {"servers": [], "databases": []},
            }
        }
    )
    rep = analyse.analyse_snapshot(paths, cost_knowledge)
    assert rep.snapshot_id == paths.snapshot_id
    assert rep.currency == "GBP"
    # Empty inventory → no Medium/High findings, only possibly Info if collectors are missing.
    crit_or_high = [
        f for f in rep.findings if f.severity in (Severity.CRITICAL, Severity.HIGH, Severity.MEDIUM)
    ]
    assert crit_or_high == []


def test_analyse_refuses_when_knowledge_ref_missing(snapshot_factory, tmp_path):
    paths = snapshot_factory({"sub-1": {}})
    empty = KnowledgeCorpus.from_path(tmp_path / "nope")  # truly empty
    with pytest.raises(analyse.KnowledgeRefMissing, match="orphaned_disks"):
        analyse.analyse_snapshot(paths, empty, only=["orphaned_disks"])


# ---- render_markdown ---------------------------------------------------------


def test_markdown_headline_renders_savings_and_severity_counts():
    r = _report(
        [
            _finding(
                rule_id="r1",
                severity=Severity.HIGH,
                estimated_savings=SavingsRange(
                    low_gbp_per_month=Decimal("100"),
                    high_gbp_per_month=Decimal("200"),
                    assumption="x",
                ),
            ),
            _finding(
                rule_id="r2",
                severity=Severity.MEDIUM,
                estimated_savings=SavingsRange(
                    low_gbp_per_month=Decimal("20"),
                    high_gbp_per_month=Decimal("40"),
                    assumption="y",
                ),
            ),
        ]
    )
    md = report_mod.render_markdown(r)
    assert "Total estimated monthly savings: £120 – £240 / month" in md
    assert "High: 1" in md
    assert "Medium: 1" in md
    assert "Critical: 0" in md


def test_markdown_quick_wins_pick_highest_severity_with_savings():
    r = _report(
        [
            _finding(
                rule_id="orphaned_disks",
                title="cheap orphan",
                estimated_savings=SavingsRange(
                    low_gbp_per_month=Decimal("5"), high_gbp_per_month=Decimal("10"), assumption="x"
                ),
            ),
            _finding(
                rule_id="stopped_not_deallocated_vms",
                title="stopped vm",
                severity=Severity.CRITICAL,
                confidence=Confidence.HIGH,
                knowledge_refs=["azure-advisor-cost-rules.md"],
                estimated_savings=SavingsRange(
                    low_gbp_per_month=Decimal("80"),
                    high_gbp_per_month=Decimal("160"),
                    assumption="x",
                ),
            ),
        ]
    )
    md = report_mod.render_markdown(r)
    assert md.index("stopped vm") < md.index("cheap orphan")


def test_markdown_strategic_recommendations_pick_recurring_groups():
    findings = [
        _finding(
            rule_id="untagged_costly_resources",
            title=f"sa-{i} missing accounting",
            severity=Severity.LOW,
            confidence=Confidence.HIGH,
            resource_name=f"sa-{i}",
            knowledge_refs=["tagging-and-governance.md", "finops-framework.md"],
        )
        for i in range(10)
    ]
    md = report_mod.render_markdown(_report(findings))
    assert "untagged_costly_resources" in md
    # 10 should be summarised, not listed individually
    assert "10 resource(s)" in md
    # Only the first 5 sample names appear
    assert "sa-0" in md and "sa-4" in md
    assert "and 5 more" in md


def test_markdown_info_findings_grouped_with_count():
    findings = [
        _finding(
            rule_id="idle_vms",
            title=f"Idle VM check: insufficient metrics for vm-{i}",
            severity=Severity.INFO,
            confidence=Confidence.HIGH,
            knowledge_refs=[],
        )
        for i in range(8)
    ]
    md = report_mod.render_markdown(_report(findings))
    assert "Info findings (8)" in md
    assert "idle_vms — 8 item(s)" in md
    assert "and 3 more" in md


def test_markdown_footer_states_read_only():
    md = report_mod.render_markdown(_report([_finding()]))
    assert "Read-only analysis" in md
    assert "no `az` write commands" in md


def test_yaml_output_is_valid_yaml_with_findings_array():
    r = _report([_finding()])
    out = report_mod.render_yaml(r)
    parsed = yaml.safe_load(out)
    assert parsed["snapshot_id"] == "2026-04-29T10-00-00Z"
    assert isinstance(parsed["findings"], list)
    assert parsed["findings"][0]["rule_id"] == "orphaned_disks"
