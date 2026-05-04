"""advisor_cost_recommendations — surface Microsoft Azure Advisor's cost
recommendations as findings, with their published savings figures.

Microsoft Advisor pre-computes savings against the customer's actual usage
for RIs, savings plans, right-sizing, idle resources, and Log Analytics
configuration. Those numbers are higher-confidence than any retail-rate
estimate we can derive ourselves. This rule reads `advisor.json` (already
collected by the `advisor` collector) and emits one Finding per
Cost-category recommendation, mapping Advisor's `impact` directly onto
our severity. Microsoft owns the savings figure; we are a faithful relay.

Authority: `azure-advisor-cost-rules.md`. The savings amount comes from
`extendedProperties.annualSavingsAmount` in Advisor's payload. We FX-convert
USD → GBP at a configurable rate (`ctx.config["fx_usd_gbp"]`, default 0.79).
"""

from __future__ import annotations

from collections.abc import Iterable

from azure_investigator_core.schema import Confidence, Finding, Severity

from .base import RuleContext, savings_range

RULE_ID = "advisor_cost_recommendations"
KNOWLEDGE_REFS = ["azure-advisor-cost-rules.md", "pricing-sources.md"]

DEFAULT_FX_USD_GBP = 0.79

_IMPACT_MAP = {
    "High": Severity.HIGH,
    "Medium": Severity.MEDIUM,
    "Low": Severity.LOW,
}


def _category(rec: dict) -> str:
    return rec.get("category") or (rec.get("properties") or {}).get("category") or ""


def _monthly_gbp(annual: object, currency: object, fx: float) -> float | None:
    if annual is None:
        return None
    try:
        amount = float(annual)
    except (TypeError, ValueError):
        return None
    if amount <= 0:
        return None
    cur = (currency or "").upper() if isinstance(currency, str) else ""
    if cur == "USD":
        amount *= fx
    elif cur and cur != "GBP":
        # Unknown currency — surface the recommendation but skip the band.
        return None
    return amount / 12.0


def evaluate(ctx: RuleContext) -> Iterable[Finding]:
    fx = float(ctx.config.get("fx_usd_gbp", DEFAULT_FX_USD_GBP))
    findings: list[Finding] = []
    for sub in ctx.subscriptions():
        records = ctx.data_for(sub.id, "advisor") or []
        for rec in records:
            if _category(rec) != "Cost":
                continue
            ep = rec.get("extendedProperties") or {}
            impact = rec.get("impact") or "Medium"
            severity = _IMPACT_MAP.get(impact, Severity.MEDIUM)
            short = rec.get("shortDescription") or {}
            problem = short.get("problem") or rec.get("name", "Advisor recommendation")
            sku = ep.get("sku")
            sub_cat = ep.get("recommendationSubCategory") or "Unspecified"

            monthly = _monthly_gbp(ep.get("annualSavingsAmount"), ep.get("savingsCurrency"), fx)
            estimated_savings = None
            if monthly is not None:
                # Microsoft publishes a point estimate; band ±10% to keep the
                # report's high/low convention without over-claiming.
                estimated_savings = savings_range(
                    round(monthly * 0.9, 2),
                    round(monthly * 1.1, 2),
                    assumption=(
                        f"Microsoft Advisor estimate: "
                        f"{ep.get('annualSavingsAmount')} "
                        f"{ep.get('savingsCurrency') or 'USD'}/yr, "
                        f"FX-converted at USD/GBP {fx:.2f}. Microsoft computes "
                        "this against this tenant's 30-day actual usage; "
                        "treat it as the high-confidence figure for the "
                        "recommendation but net out negotiated discounts and "
                        "any overlapping commitments before booking it."
                    ),
                )

            title_parts = [problem]
            if sku:
                title_parts.append(sku)
            title = "[Advisor] " + ": ".join(title_parts)

            findings.append(
                Finding(
                    rule_id=RULE_ID,
                    subscription_id=sub.id,
                    subscription_name=sub.name,
                    region=ep.get("regionId"),
                    resource_id=rec.get("id"),
                    resource_name=ep.get("impactedValue") or rec.get("name"),
                    title=title,
                    severity=severity,
                    confidence=Confidence.HIGH,
                    estimated_savings=estimated_savings,
                    knowledge_refs=KNOWLEDGE_REFS,
                    evidence={
                        "advisor_recommendation_type_id": rec.get("recommendationTypeId"),
                        "advisor_subcategory": sub_cat,
                        "advisor_impact": impact,
                        "annual_savings": ep.get("annualSavingsAmount"),
                        "savings_currency": ep.get("savingsCurrency"),
                        "sku": sku,
                        "term": ep.get("term"),
                        "scope": ep.get("scope"),
                        "lookback_days": ep.get("lookbackPeriod"),
                    },
                    recommended_investigation=(
                        f"Advisor sub-category: {sub_cat}. Open Azure Portal → "
                        "Advisor → Cost to see the specific resource and any "
                        "one-click action. Microsoft's savings figure is "
                        "computed against this tenant's 30-day usage; "
                        "RI/Savings-plan recommendations across categories "
                        "(VM RI vs Compute SP vs App Service RI) often "
                        "overlap — picking one strategy excludes others, so "
                        "do not sum the bands across overlapping "
                        "recommendations when committing to a plan."
                    ),
                )
            )
    return findings
