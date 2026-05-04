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


# ---------------------------------------------------------------------------- #
# Headline de-overlap for Advisor cost recommendations.
#
# Microsoft Advisor publishes overlapping commitment recommendations: a
# Compute Savings Plan and a set of VM Reserved Instance recommendations
# can both target the same compute. Picking one strategy excludes the
# other for those resources, so summing both into the headline overstates
# capturable savings. Per-finding detail in the report stays unchanged —
# this only governs the "Total estimated monthly savings" line.
#
# Clustering rules per subscription:
#   - VM RIs (Reservations, sku Standard_*) and Compute Savings Plans are
#     alternatives → take max(sum(VM RIs), sum(Compute SPs)).
#   - App Service RIs are additive across plans (each plan needs its own).
#   - Database SP is independent of compute commitments.
#   - Anything else (Spot, Container Insights, Basic logs, etc.) is additive.

ADVISOR_RULE_ID = "advisor_cost_recommendations"


def _advisor_cluster_key(sub_cat: str, sku: str) -> tuple[str, str]:
    """Return (cluster, class). Cluster groups overlapping recommendations;
    class distinguishes the alternatives within an overlapping cluster."""
    sub_cat = sub_cat or ""
    sku = sku or ""
    if sub_cat == "Reservations" and sku.startswith("Standard_"):
        return ("compute_commitment", "ri")
    if sub_cat == "SavingsPlan" and "Compute_Savings_Plan" in sku:
        return ("compute_commitment", "sp")
    if sub_cat == "Reservations" and sku.startswith("Azure_App_Service_"):
        return ("app_service_ri", "ri")
    if sub_cat == "SavingsPlan" and "Database_Savings_Plan" in sku:
        return ("database_sp", "sp")
    return (f"other:{sub_cat}:{sku or 'na'}", "other")


def _sum_bands(findings: Iterable[Finding]) -> tuple[Decimal, Decimal]:
    low, high = Decimal("0"), Decimal("0")
    for f in findings:
        if f.estimated_savings is None:
            continue
        low += f.estimated_savings.low_gbp_per_month
        high += f.estimated_savings.high_gbp_per_month
    return low, high


def _advisor_de_overlap_total(findings: list[Finding]) -> tuple[Decimal, Decimal]:
    """Compute Advisor savings with alternatives collapsed (max-of, not sum)."""
    # sub_id -> cluster -> class -> [findings]
    by_sub: dict[str, dict[str, dict[str, list[Finding]]]] = defaultdict(
        lambda: defaultdict(lambda: defaultdict(list))
    )
    for f in findings:
        sub_cat = (f.evidence or {}).get("advisor_subcategory") or ""
        sku = (f.evidence or {}).get("sku") or ""
        cluster, klass = _advisor_cluster_key(sub_cat, sku)
        by_sub[f.subscription_id][cluster][klass].append(f)

    total_low = Decimal("0")
    total_high = Decimal("0")
    for clusters in by_sub.values():
        for cluster, classes in clusters.items():
            if cluster == "compute_commitment":
                ri_low, ri_high = _sum_bands(classes.get("ri", []))
                sp_low, sp_high = _sum_bands(classes.get("sp", []))
                total_low += max(ri_low, sp_low)
                total_high += max(ri_high, sp_high)
            else:
                for klass_findings in classes.values():
                    low, high = _sum_bands(klass_findings)
                    total_low += low
                    total_high += high
    return total_low, total_high


def _headline_total(findings: Iterable[Finding]) -> tuple[Decimal, Decimal]:
    """Total monthly savings for the headline, with Advisor alternatives
    collapsed to the larger of (RI sum, SP sum) per subscription. Other
    findings sum normally."""
    findings = list(findings)
    advisor = [f for f in findings if f.rule_id == ADVISOR_RULE_ID]
    other = [f for f in findings if f.rule_id != ADVISOR_RULE_ID]
    other_low, other_high = _savings_total(other)
    advisor_low, advisor_high = _advisor_de_overlap_total(advisor)
    return other_low + advisor_low, other_high + advisor_high


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
    low, high = _headline_total(findings)
    naive_low, naive_high = _savings_total(findings)
    advisor_overlap_collapsed = (naive_high - high) > 0

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
    lines.append(
        "_Severity is assigned by the high end of the savings band: "
        "Critical ≥ £1,500/mo, High ≥ £200/mo, Medium ≥ £30/mo, Low otherwise. "
        "Findings with no savings band (governance, tagging, env mismatch) "
        "keep the rule-authored severity._"
    )
    if advisor_overlap_collapsed:
        lines.append("")
        lines.append(
            f"_Advisor commitment recommendations are de-overlapped: VM "
            f"Reserved Instances and Compute Savings Plans target the same "
            f"compute, so the headline takes the larger of the two per "
            f"subscription rather than summing. Naive sum (with overlap "
            f"double-counted) would be {_gbp(naive_low)} – {_gbp(naive_high)} "
            f"/ month._"
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


# ---------------------------------------------------------------------------- #
# HTML render — wraps the markdown render in a self-contained HTML document
# with print-friendly CSS so the report doubles as an email attachment / PDF
# source.

_HTML_CSS = """
:root { --fg: #0f172a; --muted: #475569; --bg: #ffffff; --accent: #1d4ed8;
        --border: #e2e8f0; --code-bg: #f1f5f9; }
* { box-sizing: border-box; }
body { font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Helvetica,
        Arial, sans-serif; color: var(--fg); background: var(--bg);
        max-width: 920px; margin: 32px auto; padding: 0 24px;
        line-height: 1.55; }
h1, h2, h3 { line-height: 1.25; }
h1 { font-size: 28px; border-bottom: 2px solid var(--border);
        padding-bottom: 8px; }
h2 { font-size: 22px; margin-top: 32px; border-bottom: 1px solid var(--border);
        padding-bottom: 4px; }
h3 { font-size: 17px; margin-top: 24px; color: var(--muted); }
p, li { font-size: 15px; }
em { color: var(--muted); }
strong { color: var(--fg); }
a { color: var(--accent); text-decoration: none; }
a:hover { text-decoration: underline; }
code { background: var(--code-bg); padding: 1px 5px; border-radius: 3px;
        font-size: 13px; }
pre { background: var(--code-bg); padding: 12px 16px; border-radius: 6px;
        overflow-x: auto; font-size: 13px; }
ul, ol { padding-left: 22px; }
li { margin: 4px 0; }
hr { border: none; border-top: 1px solid var(--border); margin: 24px 0; }
blockquote { border-left: 3px solid var(--border); margin: 16px 0;
        padding: 4px 14px; color: var(--muted); }
table { border-collapse: collapse; width: 100%; margin: 12px 0;
        font-size: 14px; }
th, td { border: 1px solid var(--border); padding: 6px 10px; text-align: left; }
th { background: #f8fafc; }
@media print {
    body { margin: 0; max-width: none; }
    h2 { page-break-before: auto; }
    a { color: var(--fg); text-decoration: none; }
}
"""


def render_html(report: Report, *, title: str | None = None) -> str:
    """Self-contained HTML document with print-friendly CSS.

    The markdown render is the source of truth; we convert it once here.
    Designed to double as an email attachment or PDF source (browser
    print-to-PDF works without further tooling).
    """
    from markdown_it import MarkdownIt

    md_text = render_markdown(report)
    md = MarkdownIt("commonmark", {"breaks": False, "html": False}).enable("table")
    body_html = md.render(md_text)
    page_title = title or f"Azure cost review — {report.snapshot_id}"
    return (
        "<!DOCTYPE html>\n"
        '<html lang="en">\n'
        "<head>\n"
        '<meta charset="utf-8">\n'
        '<meta name="viewport" content="width=device-width, initial-scale=1">\n'
        f"<title>{page_title}</title>\n"
        f"<style>{_HTML_CSS}</style>\n"
        "</head>\n"
        f"<body>\n{body_html}\n</body>\n"
        "</html>\n"
    )
