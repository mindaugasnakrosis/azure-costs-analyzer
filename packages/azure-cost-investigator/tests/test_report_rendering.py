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


def _advisor(
    *,
    subscription_id="sub-1",
    sub_cat,
    sku,
    monthly_low,
    monthly_high,
    severity=Severity.HIGH,
    title=None,
):
    return _finding(
        rule_id="advisor_cost_recommendations",
        title=title or f"[Advisor] {sub_cat}: {sku}",
        subscription_id=subscription_id,
        severity=severity,
        confidence=Confidence.HIGH,
        knowledge_refs=["azure-advisor-cost-rules.md"],
        evidence={"advisor_subcategory": sub_cat, "sku": sku},
        estimated_savings=SavingsRange(
            low_gbp_per_month=Decimal(str(monthly_low)),
            high_gbp_per_month=Decimal(str(monthly_high)),
            assumption="Microsoft Advisor estimate (test fixture).",
        ),
        recommended_investigation="see Advisor",
    )


# ---- headline de-overlap -----------------------------------------------------


def test_compute_ri_and_compute_sp_are_alternatives_max_wins():
    findings = [
        # Two VM RIs in the same sub: additive within RI cluster, summing to 1100.
        _advisor(sub_cat="Reservations", sku="Standard_D4ds_v5", monthly_low=400, monthly_high=600),
        _advisor(sub_cat="Reservations", sku="Standard_D4ds_v5", monthly_low=300, monthly_high=500),
        # One Compute Savings Plan in the same sub at 700/mo.
        _advisor(
            sub_cat="SavingsPlan", sku="Compute_Savings_Plan", monthly_low=600, monthly_high=700
        ),
    ]
    low, high = report_mod._headline_total(findings)
    # RI sum: low=700 high=1100. SP sum: low=600 high=700. Max wins: low=700 high=1100.
    assert low == Decimal("700")
    assert high == Decimal("1100")


def test_compute_sp_wins_when_larger_than_ri_sum():
    findings = [
        _advisor(sub_cat="Reservations", sku="Standard_D4ds_v5", monthly_low=100, monthly_high=200),
        _advisor(
            sub_cat="SavingsPlan", sku="Compute_Savings_Plan", monthly_low=600, monthly_high=900
        ),
    ]
    low, high = report_mod._headline_total(findings)
    assert low == Decimal("600")
    assert high == Decimal("900")


def test_app_service_ri_is_additive_not_alternative_to_compute_sp():
    findings = [
        # App Service RIs across two plans → additive (each plan needs its own RI).
        _advisor(
            sub_cat="Reservations",
            sku="Azure_App_Service_Premium_v3_Plan_Linux_P3_v3",
            monthly_low=100,
            monthly_high=200,
        ),
        _advisor(
            sub_cat="Reservations",
            sku="Azure_App_Service_Premium_v3_Plan_Linux_P3_v3",
            monthly_low=150,
            monthly_high=250,
        ),
        # Compute SP — separate compute family, doesn't overlap App Service RIs.
        _advisor(
            sub_cat="SavingsPlan", sku="Compute_Savings_Plan", monthly_low=300, monthly_high=400
        ),
    ]
    low, high = report_mod._headline_total(findings)
    # All three should sum cleanly.
    assert low == Decimal("550")
    assert high == Decimal("850")


def test_database_sp_is_independent_of_compute_alternatives():
    findings = [
        _advisor(sub_cat="Reservations", sku="Standard_D4ds_v5", monthly_low=400, monthly_high=500),
        _advisor(
            sub_cat="SavingsPlan", sku="Compute_Savings_Plan", monthly_low=600, monthly_high=700
        ),
        _advisor(
            sub_cat="SavingsPlan",
            sku="Database_Savings_Plan",
            monthly_low=100,
            monthly_high=150,
        ),
    ]
    low, high = report_mod._headline_total(findings)
    # Compute cluster: max(400,600)=600 / max(500,700)=700. Plus DB SP additive.
    assert low == Decimal("700")
    assert high == Decimal("850")


def test_overlap_collapse_is_per_subscription():
    findings = [
        # Sub-1: RI sum=200, SP=300 → SP wins.
        _advisor(
            subscription_id="sub-1",
            sub_cat="Reservations",
            sku="Standard_D4ds_v5",
            monthly_low=100,
            monthly_high=200,
        ),
        _advisor(
            subscription_id="sub-1",
            sub_cat="SavingsPlan",
            sku="Compute_Savings_Plan",
            monthly_low=200,
            monthly_high=300,
        ),
        # Sub-2: RI sum=500, SP=100 → RI wins.
        _advisor(
            subscription_id="sub-2",
            sub_cat="Reservations",
            sku="Standard_D4ds_v5",
            monthly_low=400,
            monthly_high=500,
        ),
        _advisor(
            subscription_id="sub-2",
            sub_cat="SavingsPlan",
            sku="Compute_Savings_Plan",
            monthly_low=50,
            monthly_high=100,
        ),
    ]
    low, high = report_mod._headline_total(findings)
    # sub-1: low=200 high=300 (SP). sub-2: low=400 high=500 (RI). Total: 600 / 800.
    assert low == Decimal("600")
    assert high == Decimal("800")


def test_non_advisor_findings_sum_normally():
    findings = [
        _finding(
            rule_id="orphaned_disks",
            estimated_savings=SavingsRange(
                low_gbp_per_month=Decimal("30"),
                high_gbp_per_month=Decimal("40"),
                assumption="x",
            ),
        ),
        _advisor(sub_cat="Reservations", sku="Standard_D4ds_v5", monthly_low=400, monthly_high=500),
        _advisor(
            sub_cat="SavingsPlan", sku="Compute_Savings_Plan", monthly_low=600, monthly_high=700
        ),
    ]
    low, high = report_mod._headline_total(findings)
    # disks 30/40 + max(RI 400-500, SP 600-700) → 630 / 740
    assert low == Decimal("630")
    assert high == Decimal("740")


def test_render_markdown_shows_de_overlap_note_when_collapse_changed_total():
    findings = [
        _advisor(sub_cat="Reservations", sku="Standard_D4ds_v5", monthly_low=400, monthly_high=500),
        _advisor(
            sub_cat="SavingsPlan", sku="Compute_Savings_Plan", monthly_low=600, monthly_high=700
        ),
    ]
    md = report_mod.render_markdown(_report(findings))
    assert "de-overlapped" in md
    # The naive sum should also be cited so the user can see what was removed.
    assert "Naive sum" in md
    # Headline = max(RI, SP) = 600 / 700.
    assert "£600 – £700 / month" in md


def test_render_markdown_omits_note_when_no_collapse_happened():
    findings = [
        _finding(
            rule_id="orphaned_disks",
            estimated_savings=SavingsRange(
                low_gbp_per_month=Decimal("30"),
                high_gbp_per_month=Decimal("40"),
                assumption="x",
            ),
        ),
    ]
    md = report_mod.render_markdown(_report(findings))
    assert "de-overlapped" not in md


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


def test_html_render_is_self_contained_document():
    r = _report([_finding()])
    html = report_mod.render_html(r)
    assert html.startswith("<!DOCTYPE html>")
    assert "</html>" in html.rstrip()
    # CSS is inlined so the artefact is a single self-contained file.
    assert "<style>" in html and "</style>" in html
    # Title reflects the snapshot id.
    assert "2026-04-29T10-00-00Z" in html
    # Body content survives the markdown→html conversion.
    assert "Orphaned managed disk" in html


def test_html_render_includes_severity_and_savings():
    r = _report(
        [
            _finding(
                title="Orphaned disk: foo",
                estimated_savings=SavingsRange(
                    low_gbp_per_month=Decimal("31"),
                    high_gbp_per_month=Decimal("38"),
                    assumption="retail rate",
                ),
            )
        ]
    )
    html = report_mod.render_html(r)
    # Headline shows the £ figures from the markdown source.
    assert "£31" in html
    assert "£38" in html


def test_html_custom_title():
    r = _report([_finding()])
    html = report_mod.render_html(r, title="My custom title")
    assert "<title>My custom title</title>" in html
