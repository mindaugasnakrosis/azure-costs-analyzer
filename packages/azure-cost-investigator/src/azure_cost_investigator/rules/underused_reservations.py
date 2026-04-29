"""underused_reservations — reservations whose 30-day utilisation is below the
configured threshold (default 80%, FinOps Foundation guidance).

Authority: `knowledge/reservations-utilisation.md`. Microsoft does not publish
a single numeric "underused" threshold; the FinOps Foundation Rate
Optimization capability suggests <80% over a 30-day window as the review
flag. We expose the threshold via `ctx.config["reservation_min_utilisation"]`.

The collector returns each reservation order with nested `reservations: [...]`
detail records. The Cost Management API surfaces utilisation under a
non-standard property name across versions; we attempt several candidates and
emit Info if none are present.

Severity: Medium. Confidence: Medium (threshold is not Microsoft-authoritative).
"""

from __future__ import annotations

from collections.abc import Iterable

from azure_investigator_core.schema import Confidence, Finding, Severity

from .base import RuleContext, info_missing_data

RULE_ID = "underused_reservations"
KNOWLEDGE_REFS = [
    "reservations-utilisation.md",
    "azure-advisor-cost-rules.md",
    "azure-well-architected-cost.md",
    "finops-framework.md",
]

DEFAULT_MIN_UTILISATION_PCT = 80.0

# Property names where utilisation has been seen. The collector merges
# `avgUtilizationPercentage` from `az consumption reservation summary list`
# (the canonical Cost Management surface); the others are kept as a fallback
# for older payload shapes.
_UTIL_KEYS = (
    "avgUtilizationPercentage",
    "utilization",
    "utilizationPercentage",
    "lastKnownUtilizationPercentage",
)


def _utilisation_pct(rsv: dict) -> float | None:
    for key in _UTIL_KEYS:
        v = rsv.get(key)
        if v is None:
            continue
        if isinstance(v, dict):
            # nested shape: {"trend": "...", "aggregates": [{"grain": "30days", "value": 73.2}]}
            for agg in v.get("aggregates") or []:
                if str(agg.get("grain", "")).lower().startswith("30"):
                    val = agg.get("value")
                    if val is not None:
                        try:
                            return float(val)
                        except (TypeError, ValueError):
                            return None
            continue
        try:
            return float(v)
        except (TypeError, ValueError):
            continue
    return None


def evaluate(ctx: RuleContext) -> Iterable[Finding]:
    findings: list[Finding] = []
    threshold = float(ctx.config.get("reservation_min_utilisation", DEFAULT_MIN_UTILISATION_PCT))
    for sub in ctx.subscriptions():
        records = ctx.data_for(sub.id, "reservations")
        if records is None:
            findings.append(
                info_missing_data(
                    rule_id=RULE_ID,
                    title="Reservations utilisation",
                    subscription=sub,
                    missing_collector="reservations",
                )
            )
            continue
        for entry in records:
            order = entry.get("order") or {}
            for rsv in entry.get("reservations") or []:
                util = _utilisation_pct(rsv)
                rsv_props = rsv.get("properties") or rsv
                sku_name = rsv_props.get("skuName") or (rsv.get("sku") or {}).get("name", "Unknown")
                rsv_name = rsv.get("name") or rsv_props.get("displayName") or sku_name
                base = dict(
                    rule_id=RULE_ID,
                    subscription_id=sub.id,
                    subscription_name=sub.name,
                    region=rsv_props.get("appliedScopeType") or order.get("displayName"),
                    resource_id=rsv.get("id") or order.get("id"),
                    resource_name=str(rsv_name),
                    knowledge_refs=KNOWLEDGE_REFS,
                )
                if util is None:
                    findings.append(
                        Finding(
                            **base,
                            title=f"Reservation utilisation unknown: {rsv_name}",
                            severity=Severity.INFO,
                            confidence=Confidence.HIGH,
                            evidence={
                                "sku": sku_name,
                                "reason": "no utilisation field in collector payload",
                            },
                            recommended_investigation=(
                                "Re-run the reservations collector after "
                                "ensuring the `reservation` extension is "
                                "current (`az extension update --name "
                                "reservation`); some API versions hide "
                                "utilisation in a different property."
                            ),
                        )
                    )
                    continue
                if util >= threshold:
                    continue
                findings.append(
                    Finding(
                        **base,
                        title=(
                            f"Underused reservation ({util:.1f}% over 30d, "
                            f"target ≥{threshold:.0f}%): {rsv_name}"
                        ),
                        severity=Severity.MEDIUM,
                        confidence=Confidence.MEDIUM,
                        evidence={
                            "utilisation_pct": util,
                            "threshold_pct": threshold,
                            "sku": sku_name,
                        },
                        recommended_investigation=(
                            "Threshold is FinOps Foundation guidance, not a "
                            "Microsoft-published number. Confirm with the "
                            "reservation owner whether the under-utilisation "
                            "is expected (e.g. workload not yet migrated) or "
                            "if the scope/SKU should be adjusted."
                        ),
                    )
                )
    return findings
