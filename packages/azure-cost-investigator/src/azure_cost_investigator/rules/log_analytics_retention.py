"""log_analytics_retention — flag Log Analytics workspaces whose retention
exceeds the 31-day free band, or which run on a legacy SKU.

Authority: `log-analytics-retention.md`. The rule emits one Finding per
workspace that meets a flagging condition, with a savings band derived
from the consumption snapshot's Log-Analytics line for that workspace's
resource ID — when present. Without consumption data the finding still
surfaces (governance value) but without a band.
"""

from __future__ import annotations

from collections.abc import Iterable
from decimal import Decimal

from azure_investigator_core.schema import Confidence, Finding, Severity

from .base import RuleContext, info_missing_data, savings_range

RULE_ID = "log_analytics_retention"
KNOWLEDGE_REFS = ["log-analytics-retention.md", "pricing-sources.md"]

FREE_RETENTION_DAYS = 31

# SKUs Microsoft still bills as "current". Anything else is legacy and
# itself worth flagging (independent of retention).
_CURRENT_SKUS = frozenset({"pergb2018", "capacityreservation"})

# Microsoft's "30–50% recoverable on workspaces over 90 days retention"
# headline; we apply a conservative band against the 30-day spend.
DEFAULT_LOW_FACTOR = 0.20
DEFAULT_HIGH_FACTOR = 0.40

_LA_METER_CATEGORY = "Log Analytics"


def _consumption_rows(consumption: object) -> list[dict]:
    if isinstance(consumption, list):
        return consumption
    if isinstance(consumption, dict):
        rows = consumption.get("actual")
        if isinstance(rows, list):
            return rows
    return []


def _workspace_30d_gbp(consumption: object, workspace_id: str) -> Decimal | None:
    rows = _consumption_rows(consumption)
    if not rows or not workspace_id:
        return None
    target = workspace_id.lower()
    total = Decimal("0")
    saw_match = False
    for row in rows:
        if not isinstance(row, dict):
            continue
        meter = row.get("MeterCategory") or row.get("meter_category")
        if meter != _LA_METER_CATEGORY:
            continue
        rid = (row.get("ResourceId") or row.get("resource_id") or "").lower()
        if rid != target:
            continue
        currency = (row.get("Currency") or row.get("currency") or "").upper()
        if currency != "GBP":
            continue
        cost = row.get("Cost") if "Cost" in row else row.get("cost")
        try:
            total += Decimal(str(cost))
            saw_match = True
        except Exception:
            continue
    if not saw_match:
        return None
    return total


def _sku_name(ws: dict) -> str:
    sku = ws.get("sku") or {}
    return str(sku.get("name") or "").lower()


def _retention_days(ws: dict) -> int | None:
    v = ws.get("retentionInDays")
    if v is None:
        return None
    try:
        return int(v)
    except (TypeError, ValueError):
        return None


def _daily_quota_gb(ws: dict) -> float | None:
    capping = ws.get("workspaceCapping") or {}
    v = capping.get("dailyQuotaGb")
    if v is None:
        return None
    try:
        return float(v)
    except (TypeError, ValueError):
        return None


def _flagging_reason(ws: dict, retention: int | None, sku: str) -> str | None:
    """Single-string reason summarising why the workspace is flagged.

    Returns None when the workspace is on a current SKU and within the
    free retention band — nothing to flag.
    """
    is_legacy = sku and sku not in _CURRENT_SKUS
    over_retention = retention is not None and retention > FREE_RETENTION_DAYS
    quota = _daily_quota_gb(ws)
    uncapped = quota is not None and quota < 0
    parts: list[str] = []
    if over_retention:
        parts.append(f"retention {retention} days (free band ≤31)")
    if is_legacy:
        parts.append(f"legacy SKU '{sku}'")
    if uncapped and over_retention:
        parts.append("no daily cap")
    if not parts:
        return None
    return "; ".join(parts)


def _severity_for(ws: dict, retention: int | None, sku: str) -> Severity:
    if sku == "free":
        return Severity.INFO
    is_legacy = sku and sku not in _CURRENT_SKUS
    over_retention = retention is not None and retention > FREE_RETENTION_DAYS
    if over_retention or is_legacy:
        return Severity.MEDIUM
    return Severity.INFO


def evaluate(ctx: RuleContext) -> Iterable[Finding]:
    findings: list[Finding] = []
    low_factor = float(ctx.config.get("la_retention_low_factor", DEFAULT_LOW_FACTOR))
    high_factor = float(ctx.config.get("la_retention_high_factor", DEFAULT_HIGH_FACTOR))

    for sub in ctx.subscriptions():
        workspaces = ctx.data_for(sub.id, "log_analytics")
        if workspaces is None:
            findings.append(
                info_missing_data(
                    rule_id=RULE_ID,
                    title="Log Analytics retention",
                    subscription=sub,
                    missing_collector="log_analytics",
                )
            )
            continue
        consumption = ctx.data_for(sub.id, "consumption")
        for ws in workspaces:
            sku = _sku_name(ws)
            retention = _retention_days(ws)
            reason = _flagging_reason(ws, retention, sku)
            if reason is None:
                continue
            ws_id = ws.get("id") or ""
            ws_name = ws.get("name") or ws_id.rsplit("/", 1)[-1] or "unknown"
            ws_30d = _workspace_30d_gbp(consumption, ws_id)
            estimated = None
            if ws_30d and ws_30d > 0:
                estimated = savings_range(
                    round(float(ws_30d) * low_factor, 2),
                    round(float(ws_30d) * high_factor, 2),
                    assumption=(
                        f"30-day Log Analytics spend on this workspace is "
                        f"£{ws_30d:.0f}. Band applies {low_factor*100:.0f}–"
                        f"{high_factor*100:.0f}% as the typical recoverable "
                        f"share by shortening interactive retention or "
                        f"moving cold data to the archive tier (Microsoft's "
                        f"published 30–50% guidance for workspaces over "
                        f"90 days retention). Net out any audit/compliance "
                        f"requirement that pins minimum retention."
                    ),
                )
            findings.append(
                Finding(
                    rule_id=RULE_ID,
                    title=f"Log Analytics workspace flagged ({reason}): {ws_name}",
                    subscription_id=sub.id,
                    subscription_name=sub.name,
                    region=ws.get("location"),
                    resource_id=ws_id,
                    resource_name=ws_name,
                    severity=_severity_for(ws, retention, sku),
                    confidence=Confidence.MEDIUM,
                    estimated_savings=estimated,
                    knowledge_refs=KNOWLEDGE_REFS,
                    evidence={
                        "retention_days": retention,
                        "sku": sku or None,
                        "daily_quota_gb": _daily_quota_gb(ws),
                        "reason": reason,
                    },
                    recommended_investigation=(
                        "Confirm with the workspace owner what audit / "
                        "compliance contract pins retention. If interactive "
                        "retention exceeds operational query needs (most "
                        "incident-response workflows touch only the last "
                        "7–30 days), per-table retention overrides or a "
                        "move to the archive tier release the bulk of the "
                        "cost. For legacy SKUs, migrate to PerGB2018 or a "
                        "CapacityReservation commitment tier; Microsoft "
                        "lists Standard / Premium / PerNode as deprecated."
                    ),
                )
            )
    return findings
