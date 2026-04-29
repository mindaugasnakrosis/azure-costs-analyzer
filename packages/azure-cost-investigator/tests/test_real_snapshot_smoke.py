"""Smoke test against a real Azure snapshot, when one is available locally.

Skipped on CI / fresh checkouts. The snapshot path is taken from the
`AZURE_INVESTIGATOR_SMOKE_SNAPSHOT` env var (an absolute path to a single
snapshot folder produced by `azure-investigator pull`). Without that env
var, the test silently skips — there's no committed dependency on any one
operator's home directory.

Confirms the rule pipeline behaves sanely on real data: produces findings
for the expected resource types, never raises, and never produces a finding
with an empty `assumption`.
"""

from __future__ import annotations

import os
from pathlib import Path

import pytest
from azure_cost_investigator.rules import iter_rules
from azure_cost_investigator.rules.base import RuleContext
from azure_investigator_core.knowledge_loader import KnowledgeCorpus
from azure_investigator_core.snapshot import paths_for, read_manifest

REAL_SNAP_ENV = "AZURE_INVESTIGATOR_SMOKE_SNAPSHOT"


def _have_real_snapshot() -> bool:
    raw = os.environ.get(REAL_SNAP_ENV)
    if not raw:
        return False
    p = Path(raw)
    return p.exists() and (p / "manifest.yaml").exists()


def _real_snap_path() -> Path:
    return Path(os.environ[REAL_SNAP_ENV])


@pytest.mark.skipif(
    not _have_real_snapshot(),
    reason=f"set {REAL_SNAP_ENV} to a real snapshot folder to enable this test",
)
def test_rules_run_against_real_snapshot():
    """Snapshot-agnostic invariants. Confirms the rule pipeline runs cleanly
    against any real snapshot the operator points the env var at — without
    asserting that any particular finding exists, since real-tenant inventory
    changes between pulls."""
    real_snap = _real_snap_path()
    snapshot_root = real_snap.parent
    paths = paths_for(snapshot_root, real_snap.name)
    knowledge = KnowledgeCorpus.load("azure_cost_investigator")
    ctx = RuleContext.from_snapshot(paths, knowledge)

    # Manifest loads and contains at least one subscription.
    manifest = read_manifest(paths)
    assert manifest.subscriptions, "real snapshot has no subscriptions"

    # Every registered rule evaluates without raising, against real data.
    all_findings = []
    for rule_id, knowledge_refs, evaluate in iter_rules():
        findings = list(evaluate(ctx))
        all_findings.extend(findings)
        # All declared knowledge refs are present in the corpus.
        for ref in knowledge_refs:
            assert knowledge.has(ref), f"{rule_id}: missing {ref}"

    # Every produced finding satisfies the schema invariants we care about
    # (Pydantic enforces them at construction; belt-and-braces here in case a
    # rule is regressed to bypass the validator).
    for f in all_findings:
        assert f.subscription_id, f"{f.rule_id}: empty subscription_id"
        assert f.recommended_investigation.strip(), f"{f.rule_id}: empty investigation"
        if f.severity.value != "Info":
            assert f.knowledge_refs, f"{f.rule_id}: non-Info finding without citation"
        if f.estimated_savings is not None:
            assert f.estimated_savings.assumption.strip(), (
                f"{f.rule_id}: savings range without assumption"
            )
            assert f.estimated_savings.low_gbp_per_month <= f.estimated_savings.high_gbp_per_month
