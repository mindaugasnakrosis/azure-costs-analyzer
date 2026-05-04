"""Rule dispatcher.

`analyse_snapshot()` walks the registry, refuses to run any rule whose
declared `KNOWLEDGE_REFS` are missing from the corpus (hard rule from PRD §10),
and aggregates the resulting Findings into a Report.

After rules emit, three post-passes run before the Report is built:

1. `_dedup_resource_overlaps` collapses pairs of rules that flag the same
   waste on the same resource — currently `idle_vms` + `oversized_vms` for
   one VM (deallocate is the higher-impact action; resizing an idle VM
   doesn't fix the underlying waste).
2. `_dedup_billing_scope_findings` collapses billing-account-scope findings
   that surface in every subscription where their collector runs — chiefly
   `underused_reservations`, since reservations are billing-scope. Without
   this pass each reservation would be counted N times in the headline
   (once per subscription).
3. `_retier_by_cost` replaces each rule's hardcoded severity with the band
   derived from `estimated_savings.high_gbp_per_month`, so a £130/mo idle VM
   and a £3/mo orphan IP don't both surface as Medium.

Order matters: dedup passes run before re-tier so it sees the post-collapse
bands and severity assignments are correct.
"""

from __future__ import annotations

from collections.abc import Iterable
from datetime import UTC, datetime
from decimal import Decimal

from azure_investigator_core.knowledge_loader import KnowledgeCorpus
from azure_investigator_core.pricing import PricingClient
from azure_investigator_core.schema import Finding, Report, Severity
from azure_investigator_core.snapshot import SnapshotPaths

from .rules import iter_rules
from .rules.base import RuleContext


class KnowledgeRefMissing(RuntimeError):
    """Raised when a rule's declared knowledge_refs are not in the corpus."""


# Severity thresholds, ordered Critical → Low. Each entry is the *minimum*
# `estimated_savings.high_gbp_per_month` for the band. Calibrated for a
# £30k/mo tenant; overridable via `config["severity_thresholds_gbp_month"]`.
DEFAULT_SEVERITY_THRESHOLDS_GBP_MONTH: tuple[tuple[Severity, Decimal], ...] = (
    (Severity.CRITICAL, Decimal("1500")),
    (Severity.HIGH, Decimal("200")),
    (Severity.MEDIUM, Decimal("30")),
    (Severity.LOW, Decimal("0")),
)


def _dedup_resource_overlaps(findings: list[Finding]) -> list[Finding]:
    """Drop redundant findings that flag the same waste on the same resource.

    When `idle_vms` and `oversized_vms` both fire for the same VM, the
    oversized finding is suppressed: deallocating an idle VM saves more
    than resizing it, and the pair would otherwise inflate both the triage
    list and the £/mo headline. The kept (idle) finding gets a one-line
    note in `recommended_investigation` so the suppression is visible.
    """
    by_resource: dict[tuple[str, str], dict[str, Finding]] = {}
    for f in findings:
        if f.resource_id:
            by_resource.setdefault((f.subscription_id, f.resource_id), {})[f.rule_id] = f

    suppress: set[int] = set()
    annotate: dict[int, str] = {}
    for bucket in by_resource.values():
        if "idle_vms" in bucket and "oversized_vms" in bucket:
            suppress.add(id(bucket["oversized_vms"]))
            annotate[id(bucket["idle_vms"])] = (
                " The oversized-VM check also flagged this VM; suppressed to "
                "avoid double-counting — deallocate is the higher-impact action."
            )

    out: list[Finding] = []
    for f in findings:
        if id(f) in suppress:
            continue
        note = annotate.get(id(f))
        if note:
            f = f.model_copy(
                update={"recommended_investigation": f.recommended_investigation + note}
            )
        out.append(f)
    return out


# Rules whose findings are billing-account-scope (i.e. would naturally
# duplicate across every subscription where their collector ran). The dedup
# key is the rule_id + the leaf identifier of `resource_id`.
_BILLING_SCOPE_RULES: frozenset[str] = frozenset({"underused_reservations"})


def _dedup_billing_scope_findings(findings: list[Finding]) -> list[Finding]:
    """Collapse billing-scope findings that surface in every subscription.

    Reservations live at the billing-account scope, so the reservations
    collector returns the same orders for every subscription it runs against.
    Without dedup, a single £100/mo underused reservation in a tenant with
    two subscriptions would inflate the headline to £200/mo.

    Strategy: keep the finding with the **highest** `estimated_savings.high`
    band per `(rule_id, resource_id_leaf)` — that's the run with the most
    information. Drop the rest. If the kept finding has a band, append a
    note listing the other subscriptions that also surfaced the same record
    so the dedup is visible in the report.
    """

    def _leaf(rid: str | None) -> str | None:
        if not rid:
            return None
        return rid.rsplit("/", 1)[-1] or None

    def _band_high_value(f: Finding) -> Decimal:
        if f.estimated_savings is None:
            return Decimal("-1")
        return f.estimated_savings.high_gbp_per_month

    by_key: dict[tuple[str, str], list[Finding]] = {}
    keys: dict[int, tuple[str, str]] = {}
    for f in findings:
        if f.rule_id not in _BILLING_SCOPE_RULES:
            continue
        leaf = _leaf(f.resource_id)
        if not leaf:
            continue
        key = (f.rule_id, leaf)
        by_key.setdefault(key, []).append(f)
        keys[id(f)] = key

    keepers: dict[tuple[str, str], Finding] = {}
    for key, group in by_key.items():
        keepers[key] = max(group, key=_band_high_value)

    out: list[Finding] = []
    for f in findings:
        key = keys.get(id(f))
        if key is None:
            out.append(f)
            continue
        winner = keepers[key]
        if id(f) != id(winner):
            continue
        # Annotate the kept finding when other subs surfaced the same record.
        siblings = by_key[key]
        if len(siblings) > 1:
            other_subs = sorted(
                {s.subscription_name for s in siblings if id(s) != id(winner)}
            )
            note = (
                f" Also surfaced in: {', '.join(other_subs)}. Reservations "
                f"are billing-account-scope; this finding is reported once "
                f"to avoid double-counting in the headline."
            )
            f = f.model_copy(
                update={"recommended_investigation": f.recommended_investigation + note}
            )
        out.append(f)
    return out


def _retier_by_cost(
    findings: list[Finding],
    thresholds: tuple[tuple[Severity, Decimal], ...],
) -> list[Finding]:
    """Replace severity with the band derived from `estimated_savings.high`.

    Info findings and findings without a savings band keep their authored
    severity — Info means "couldn't evaluate" (no cost signal) and
    band-less findings are typically governance issues (tagging, env
    mismatch) where rule severity carries the right meaning.
    """
    out: list[Finding] = []
    for f in findings:
        if f.severity == Severity.INFO or f.estimated_savings is None:
            out.append(f)
            continue
        high = f.estimated_savings.high_gbp_per_month
        new_sev = Severity.LOW
        for sev, threshold in thresholds:
            if high >= threshold:
                new_sev = sev
                break
        if new_sev != f.severity:
            f = f.model_copy(update={"severity": new_sev})
        out.append(f)
    return out


def analyse_snapshot(
    paths: SnapshotPaths,
    knowledge: KnowledgeCorpus,
    *,
    pricing: PricingClient | None = None,
    config: dict | None = None,
    only: Iterable[str] | None = None,
    exclude: Iterable[str] | None = None,
) -> Report:
    cfg = config or {}
    ctx = RuleContext.from_snapshot(paths, knowledge, pricing=pricing, config=cfg)
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

    findings = _dedup_resource_overlaps(findings)
    findings = _dedup_billing_scope_findings(findings)
    thresholds = cfg.get("severity_thresholds_gbp_month") or DEFAULT_SEVERITY_THRESHOLDS_GBP_MONTH
    findings = _retier_by_cost(findings, thresholds)

    return Report(
        snapshot_id=ctx.manifest.snapshot_id,
        generated_at=datetime.now(UTC),
        currency=ctx.manifest.currency or "GBP",
        findings=findings,
    )
