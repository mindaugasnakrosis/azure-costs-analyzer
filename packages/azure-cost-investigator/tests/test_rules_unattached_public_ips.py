from __future__ import annotations

from azure_cost_investigator.rules import unattached_public_ips
from azure_cost_investigator.rules.base import RuleContext
from azure_investigator_core.schema import Severity

IPS = [
    {
        "id": "/sub/ips/orphan-std",
        "name": "orphan-std",
        "location": "uksouth",
        "ipAddress": "20.0.0.1",
        "publicIPAddressVersion": "IPv4",
        "publicIPAllocationMethod": "Static",
        "ipConfiguration": None,
        "sku": {"name": "Standard"},
    },
    {
        "id": "/sub/ips/attached-std",
        "name": "attached-std",
        "location": "uksouth",
        "publicIPAddressVersion": "IPv4",
        "ipConfiguration": {"id": "/sub/nics/nic-1/ipConfigurations/ipconfig1"},
        "sku": {"name": "Standard"},
    },
    {
        "id": "/sub/ips/legacy-basic",
        "name": "legacy-basic",
        "location": "uksouth",
        "publicIPAddressVersion": "IPv4",
        "ipConfiguration": None,
        "sku": {"name": "Basic"},
    },
    {
        "id": "/sub/ips/orphan-ipv6",
        "name": "orphan-ipv6",
        "location": "uksouth",
        "publicIPAddressVersion": "IPv6",
        "ipConfiguration": None,
        "sku": {"name": "Standard"},
    },
]


def test_flags_orphan_standard_and_basic_separately(snapshot_factory, cost_knowledge):
    paths = snapshot_factory({"sub-1": {"public_ips": IPS}})
    ctx = RuleContext.from_snapshot(paths, cost_knowledge)
    findings = list(unattached_public_ips.evaluate(ctx))

    titles = {f.title: f for f in findings}
    assert "Unattached Standard public IP: orphan-std" in titles
    assert titles["Unattached Standard public IP: orphan-std"].severity == Severity.MEDIUM

    assert "Basic SKU public IP (retired tier): legacy-basic" in titles
    assert titles["Basic SKU public IP (retired tier): legacy-basic"].severity == Severity.HIGH

    # Attached and IPv6 are not flagged
    assert all("attached-std" not in t for t in titles)
    assert all("orphan-ipv6" not in t for t in titles)
    assert len(findings) == 2


def test_standard_orphan_savings_is_a_range_with_assumption(snapshot_factory, cost_knowledge):
    paths = snapshot_factory({"sub-1": {"public_ips": [IPS[0]]}})
    ctx = RuleContext.from_snapshot(paths, cost_knowledge)
    (finding,) = list(unattached_public_ips.evaluate(ctx))
    assert finding.estimated_savings is not None
    assert (
        finding.estimated_savings.low_gbp_per_month < finding.estimated_savings.high_gbp_per_month
    )
    assert "Standard SKU" in finding.estimated_savings.assumption


def test_basic_finding_omits_savings_estimate_but_carries_high_severity(
    snapshot_factory, cost_knowledge
):
    paths = snapshot_factory({"sub-1": {"public_ips": [IPS[2]]}})
    ctx = RuleContext.from_snapshot(paths, cost_knowledge)
    (finding,) = list(unattached_public_ips.evaluate(ctx))
    # Basic SKU is the architectural finding, not a numeric savings finding.
    assert finding.severity == Severity.HIGH
    assert finding.estimated_savings is None
    assert "2025-09-30" in finding.recommended_investigation


def test_missing_public_ips_collector_emits_info(snapshot_factory, cost_knowledge):
    paths = snapshot_factory({"sub-1": {"public_ips": None}})
    ctx = RuleContext.from_snapshot(paths, cost_knowledge)
    findings = list(unattached_public_ips.evaluate(ctx))
    assert len(findings) == 1
    assert findings[0].severity == Severity.INFO


def test_knowledge_refs_present(cost_knowledge):
    for ref in unattached_public_ips.KNOWLEDGE_REFS:
        assert cost_knowledge.has(ref)
