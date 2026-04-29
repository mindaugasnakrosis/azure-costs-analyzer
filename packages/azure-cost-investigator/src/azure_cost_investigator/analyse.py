"""Rule dispatcher.

`analyse_snapshot()` walks the registry, refuses to run any rule whose
declared `KNOWLEDGE_REFS` are missing from the corpus (hard rule from PRD §10),
and aggregates the resulting Findings into a Report.
"""

from __future__ import annotations

from collections.abc import Iterable
from datetime import UTC, datetime

from azure_investigator_core.knowledge_loader import KnowledgeCorpus
from azure_investigator_core.pricing import PricingClient
from azure_investigator_core.schema import Finding, Report
from azure_investigator_core.snapshot import SnapshotPaths

from .rules import iter_rules
from .rules.base import RuleContext


class KnowledgeRefMissing(RuntimeError):
    """Raised when a rule's declared knowledge_refs are not in the corpus."""


def analyse_snapshot(
    paths: SnapshotPaths,
    knowledge: KnowledgeCorpus,
    *,
    pricing: PricingClient | None = None,
    config: dict | None = None,
    only: Iterable[str] | None = None,
    exclude: Iterable[str] | None = None,
) -> Report:
    ctx = RuleContext.from_snapshot(paths, knowledge, pricing=pricing, config=config or {})
    findings: list[Finding] = []
    for rule_id, knowledge_refs, evaluate in iter_rules(only=only, exclude=exclude):
        missing = [r for r in knowledge_refs if not knowledge.has(r)]
        if missing:
            raise KnowledgeRefMissing(
                f"Rule {rule_id!r} declares knowledge_refs {missing} that are "
                "not present in the corpus. Author the missing knowledge file "
                "before re-running analyse."
            )
        findings.extend(evaluate(ctx))
    return Report(
        snapshot_id=ctx.manifest.snapshot_id,
        generated_at=datetime.now(UTC),
        currency=ctx.manifest.currency or "GBP",
        findings=findings,
    )
