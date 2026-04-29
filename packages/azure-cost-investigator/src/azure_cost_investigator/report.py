"""Markdown + YAML rendering for an analysis report.

The markdown output is the user-facing artefact. It opens with headline
numbers (severity counts, GBP savings range), surfaces top-3 quick wins and
top-3 strategic recommendations, then groups findings by severity. Low-
severity governance findings (e.g. tagging) are *summarised* rather than
listed individually so a 135-account tagging gap doesn't crowd out actually-
costly findings.

The YAML output is the flat list of findings, suitable for machine
consumption (e.g. piping into a Jira backlog by another skill — but that is
explicitly NOT this skill's responsibility).
"""

from __future__ import annotations

from collections import defaultdict
from collections.abc import Iterable
from decimal import Decimal

import yaml
from azure_investigator_core.schema import (
    Confidence,
    Finding,
    Report,
    Severity,
)

SEVERITY_ORDER: tuple[Severity, ...] = (
    Severity.CRITICAL,
    Severity.HIGH,
    Severity.MEDIUM,
    Severity.LOW,
    Severity.INFO,
)

# Findings of these rules are summarised (count + sample) rather than listed
# individually in the Low section. Avoids a 135-line tagging block burying
# the actually-costly findings.
SUMMARISE_RULES: frozenset[str] = frozenset(
    {
        "untagged_costly_resources",
    }
)


def _gbp(value: Decimal | float | int) -> str:
    return f"£{Decimal(value):,.0f}"


def _savings_total(findings: Iterable[Finding]) -> tuple[Decimal, Decimal]:
    low = Decimal("0")
    high = Decimal("0")
    for f in findings:
        if f.estimated_savings is None:
            continue
        low += f.estimated_savings.low_gbp_per_month
        high += f.estimated_savings.high_gbp_per_month
    return low, high


def _sort_key_quick_win(f: Finding) -> tuple[int, Decimal]:
    """Higher = better quick win: actively-burning Critical/High first, then
    deterministic High-confidence findings, ordered by max savings."""
    sev_rank = {
        Severity.CRITICAL: 0,
        Severity.HIGH: 1,
        Severity.MEDIUM: 2,
        Severity.LOW: 3,
        Severity.INFO: 4,
    }[f.severity]
    conf_penalty = {Confidence.HIGH: 0, Confidence.MEDIUM: 1, Confidence.LOW: 2}[f.confidence]
    high_savings = Decimal("0")
    if f.estimated_savings is not None:
        high_savings = f.estimated_savings.high_gbp_per_month
    return (sev_rank * 10 + conf_penalty, -high_savings)


def _quick_wins(report: Report, n: int = 3) -> list[Finding]:
    eligible = [
        f
        for f in report.findings
        if f.severity in (Severity.CRITICAL, Severity.HIGH, Severity.MEDIUM)
        and f.estimated_savings is not None
    ]
    eligible.sort(key=_sort_key_quick_win)
    return eligible[:n]


def _strategic(report: Report, n: int = 3) -> list[tuple[str, list[Finding]]]:
    """Group recurring findings by rule_id where the count >= 2; return the
    top-n groups by total savings range high-end."""
    by_rule: dict[str, list[Finding]] = defaultdict(list)
    for f in report.findings:
        if f.severity == Severity.INFO:
            continue
        by_rule[f.rule_id].append(f)
    strategic: list[tuple[str, list[Finding]]] = []
    for rule_id, group in by_rule.items():
        if len(group) < 2:
            continue
        strategic.append((rule_id, group))

    def group_score(item: tuple[str, list[Finding]]) -> tuple[int, Decimal]:
        _, group = item
        _, high = _savings_total(group)
        return (-len(group), -high)

    strategic.sort(key=group_score)
    return strategic[:n]


def _bulleted_finding(f: Finding) -> str:
    sub = f.subscription_name or f.subscription_id
    bits = [f"**{f.title}** _(sub: {sub}"]
    if f.region:
        bits.append(f", region: {f.region}")
    bits.append(")_")
    line1 = "".join(bits)
    parts = [f"- {line1}"]
    if f.estimated_savings is not None:
        parts.append(
            f"  Estimated savings: {_gbp(f.estimated_savings.low_gbp_per_month)}–"
            f"{_gbp(f.estimated_savings.high_gbp_per_month)} / month. "
            f"_{f.estimated_savings.assumption}_"
        )
    parts.append(f"  Severity: {f.severity.value} · Confidence: {f.confidence.value}")
    if f.knowledge_refs:
        parts.append(f"  Authority: {', '.join(f.knowledge_refs)}")
    parts.append(f"  Recommended investigation: {f.recommended_investigation}")
    return "\n".join(parts)


def render_markdown(report: Report) -> str:
    findings = report.findings
    by_sev: dict[Severity, list[Finding]] = defaultdict(list)
    for f in findings:
        by_sev[f.severity].append(f)
    counts = {sev: len(by_sev.get(sev, [])) for sev in SEVERITY_ORDER}
    low, high = _savings_total(findings)

    lines: list[str] = []
    lines.append(f"# Azure cost review — `{report.snapshot_id}`")
    lines.append("")
    lines.append(f"_Generated: {report.generated_at.isoformat()} · Currency: {report.currency}_")
    lines.append("")

    # ---- Headline numbers ----
    lines.append("## Headline numbers")
    lines.append("")
    lines.append(f"- **Total estimated monthly savings: {_gbp(low)} – {_gbp(high)} / month**")
    lines.append("- Findings by severity:")
    for sev in SEVERITY_ORDER:
        lines.append(f"  - {sev.value}: {counts[sev]}")
    lines.append("")
    lines.append(
        "_Savings figures are GBP-converted retail rates and don't net out "
        "negotiated discounts or reservation coverage. Treat them as ceilings, "
        "not invoiced amounts._"
    )
    lines.append("")

    # ---- Top 3 quick wins ----
    qw = _quick_wins(report)
    lines.append("## Top 3 quick wins")
    lines.append("")
    if not qw:
        lines.append("_No high-confidence quick wins identified._")
    else:
        for i, f in enumerate(qw, 1):
            sav = ""
            if f.estimated_savings is not None:
                sav = (
                    f" — {_gbp(f.estimated_savings.low_gbp_per_month)}–"
                    f"{_gbp(f.estimated_savings.high_gbp_per_month)}/mo"
                )
            lines.append(
                f"{i}. **{f.title}**{sav} _(severity {f.severity.value}, confidence {f.confidence.value})_"
            )
    lines.append("")

    # ---- Top 3 strategic recommendations ----
    strat = _strategic(report)
    lines.append("## Top 3 strategic recommendations")
    lines.append("")
    if not strat:
        lines.append("_No recurring patterns above the strategic threshold._")
    else:
        for i, (rule_id, group) in enumerate(strat, 1):
            g_low, g_high = _savings_total(group)
            sav = (
                f" — total {_gbp(g_low)}–{_gbp(g_high)}/mo across {len(group)} resources"
                if g_high > 0
                else f" — across {len(group)} resources"
            )
            lines.append(f"{i}. **{rule_id}**{sav}")
            sample = group[0]
            lines.append(f"   - Example: {sample.title}")
            if sample.knowledge_refs:
                lines.append(f"   - Authority: {', '.join(sample.knowledge_refs)}")
    lines.append("")

    # ---- Findings by severity ----
    for sev in SEVERITY_ORDER:
        bucket = by_sev.get(sev, [])
        if not bucket:
            continue
        lines.append(f"## {sev.value} findings ({len(bucket)})")
        lines.append("")
        if sev == Severity.LOW:
            # Compress noisy governance findings to a count + sample.
            grouped: dict[str, list[Finding]] = defaultdict(list)
            verbose: list[Finding] = []
            for f in bucket:
                if f.rule_id in SUMMARISE_RULES:
                    grouped[f.rule_id].append(f)
                else:
                    verbose.append(f)
            for rule_id, group in grouped.items():
                lines.append(f"### {rule_id} — {len(group)} resource(s)")
                lines.append("")
                samples = group[:5]
                for f in samples:
                    lines.append(f"- {f.title}")
                if len(group) > len(samples):
                    lines.append(f"- _… and {len(group) - len(samples)} more_")
                lines.append(f"\n_Authority: {', '.join(samples[0].knowledge_refs)}._")
                lines.append(
                    f"\n_Recommended investigation_: {samples[0].recommended_investigation}"
                )
                lines.append("")
            for f in verbose:
                lines.append(_bulleted_finding(f))
                lines.append("")
        elif sev == Severity.INFO:
            # Group Info by rule_id with count + first 5 examples.
            grouped: dict[str, list[Finding]] = defaultdict(list)
            for f in bucket:
                grouped[f.rule_id].append(f)
            lines.append(
                "_Findings here mean the analyser couldn't reach a verdict — usually missing data, sparse metrics, or an API field the collector didn't capture._"
            )
            lines.append("")
            for rule_id, group in grouped.items():
                lines.append(f"### {rule_id} — {len(group)} item(s)")
                for f in group[:5]:
                    lines.append(f"- {f.title}")
                if len(group) > 5:
                    lines.append(f"- _… and {len(group) - 5} more_")
                lines.append("")
        else:
            for f in bucket:
                lines.append(_bulleted_finding(f))
                lines.append("")

    # ---- Footer ----
    lines.append("---")
    lines.append("")
    lines.append(
        "_Read-only analysis. Every claim is grounded in a `knowledge/*.md` document; "
        "no `az` write commands are issued. Findings are suggestions, not actions._"
    )
    return "\n".join(lines).rstrip() + "\n"


def render_yaml(report: Report) -> str:
    """Machine-readable findings.yaml. Flat list of findings + meta."""
    payload = report.model_dump(mode="json")
    return yaml.safe_dump(payload, sort_keys=False)
