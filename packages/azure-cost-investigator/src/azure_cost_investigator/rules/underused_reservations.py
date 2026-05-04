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

from azure_investigator_core.schema import Confidence, Finding, SavingsRange, Severity

from .base import RuleContext, info_missing_data, savings_range
from .stopped_not_deallocated_vms import _band_high, _band_low

RULE_ID = "underused_reservations"
KNOWLEDGE_REFS = [
    "reservations-utilisation.md",
    "azure-advisor-cost-rules.md",
    "azure-well-architected-cost.md",
    "finops-framework.md",
    "pricing-sources.md",
]

DEFAULT_MIN_UTILISATION_PCT = 80.0
# Default forecast horizon when the reservation's expiry isn't present in
# the snapshot. 12 months matches Microsoft's 1-year reservation term and
# converts the monthly band into a sensible "between now and expiry" figure.
DEFAULT_FORECAST_MONTHS = 12

# Microsoft's published 1-year RI discount for VMs sits in the 30–60% range
# (https://learn.microsoft.com/azure/cost-management-billing/reservations/save-compute-costs-reservations).
# We use the midpoint as a single factor: an RI is paid at ~60% of retail PAYG.
# Overridable via `ctx.config["reservation_ri_retail_factor"]`.
DEFAULT_RI_RETAIL_FACTOR = 0.60

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


# UK South Premium v3 App Service Plan retail bands (GBP/mo per instance).
# Source: https://azure.microsoft.com/en-us/pricing/details/app-service/linux/
_APP_SERVICE_BANDS = {
    "p0v3": (75.0, 100.0),
    "p1v3": (140.0, 170.0),
    "p2v3": (280.0, 340.0),
    "p3v3": (560.0, 680.0),
    "p1mv3": (180.0, 220.0),
    "p2mv3": (360.0, 440.0),
    "p3mv3": (720.0, 880.0),
}

# Premium SSD managed-disk retail bands (GBP/mo per disk).
# Source: https://azure.microsoft.com/en-us/pricing/details/managed-disks/
_PREMIUM_DISK_BANDS = {
    "p1": (1.5, 2.0),
    "p2": (3.0, 4.0),
    "p3": (5.5, 7.0),
    "p4": (8.0, 11.0),
    "p6": (10.0, 14.0),
    "p10": (14.0, 20.0),
    "p15": (25.0, 35.0),
    "p20": (50.0, 70.0),
    "p30": (100.0, 135.0),
    "p40": (200.0, 270.0),
    "p50": (400.0, 540.0),
    "p60": (800.0, 1050.0),
    "p70": (1500.0, 2000.0),
    "p80": (3000.0, 4000.0),
}


def _app_service_band(sku: str) -> tuple[float, float] | None:
    """Match `azure_app_service_premium_v3_plan_linux_p1_v3` style SKU strings.
    Real-world SKU strings use `_p1_v3` (underscore between digit and v3);
    we normalise both sides to the no-underscore form before matching.
    """
    s = sku.lower()
    if "app_service" not in s:
        return None
    s_norm = s.replace("_v3", "v3")
    for key in _APP_SERVICE_BANDS:
        if s_norm.endswith(f"_{key}") or s_norm.endswith(key):
            return _APP_SERVICE_BANDS[key]
    return None


def _premium_disk_band(sku: str) -> tuple[float, float] | None:
    """Match `Premium_SSD_Managed_Disks_P30` style SKU strings."""
    s = sku.lower()
    if "managed_disks" not in s and "managed-disks" not in s:
        return None
    for key in _PREMIUM_DISK_BANDS:
        if s.endswith(f"_{key}"):
            return _PREMIUM_DISK_BANDS[key]
    return None


def _vm_ri_savings_band(
    sku: str,
    util_pct: float,
    quantity: int,
    ri_factor: float,
) -> SavingsRange | None:
    """Estimate £/mo waste for an under-utilised reservation across the
    SKU families we have band tables for: VM (Standard_*/Basic_*), App
    Service Premium v3 plans, and Premium SSD managed disks. Returns None
    for SKUs we still can't price (SQL DTU, Cosmos RU, Synapse, ...) so
    they surface as a finding without a band.
    """
    if not sku:
        return None
    waste = max(0.0, (100.0 - util_pct) / 100.0)
    if waste == 0.0 or quantity <= 0:
        return None

    sku_lower = sku.lower()
    family_label: str
    band: tuple[float, float] | None
    if sku_lower.startswith("standard_") or sku_lower.startswith("basic_"):
        family_label = "VM"
        band = (_band_low(sku), _band_high(sku))
        if band[1] <= 0:
            band = None
    else:
        as_band = _app_service_band(sku)
        if as_band is not None:
            family_label = "App Service Plan Premium v3"
            band = as_band
        else:
            disk_band = _premium_disk_band(sku)
            if disk_band is not None:
                family_label = "Premium SSD managed disk"
                band = disk_band
            else:
                return None
    if band is None:
        return None

    monthly_low = band[0] * ri_factor * waste * quantity
    monthly_high = band[1] * ri_factor * waste * quantity
    if monthly_high <= 0:
        return None
    return savings_range(
        monthly_low,
        monthly_high,
        assumption=(
            f"Assumes 1-year RI discount at ~40% off retail PAYG (factor "
            f"{ri_factor:.2f}) for {sku} × {quantity} ({family_label}), "
            f"with {waste*100:.0f}% of reserved hours unused. Retail SKU "
            f"bands are family-level (UK South); the actual reservation "
            f"purchase price isn't in the snapshot, so treat as bounded. "
            f"Validate against the reservation order in the billing portal "
            f"before acting."
        ),
    )


def _term_remaining_months(rsv_props: dict, default_months: int) -> tuple[int, str]:
    """Compute months remaining on the reservation term.

    Reservation payloads expose `expiryDateTime` (ISO-8601) when the
    `reservation` CLI extension is current. Without it we fall back to the
    default forecast horizon (typical 1-year term). Returns
    (months_remaining, source) so the assumption can be transparent.
    """
    from datetime import UTC, datetime

    expiry = rsv_props.get("expiryDateTime") or rsv_props.get("expiryDate")
    if isinstance(expiry, str) and expiry:
        try:
            ts = datetime.fromisoformat(expiry.replace("Z", "+00:00"))
            now = datetime.now(UTC)
            delta_days = (ts - now).total_seconds() / 86400.0
            months = max(0, int(round(delta_days / 30.42)))
            if months > 0:
                return months, "snapshot.expiryDateTime"
        except (ValueError, TypeError):
            pass
    return default_months, "default 12-month forecast horizon"


def evaluate(ctx: RuleContext) -> Iterable[Finding]:
    findings: list[Finding] = []
    threshold = float(ctx.config.get("reservation_min_utilisation", DEFAULT_MIN_UTILISATION_PCT))
    ri_factor = float(ctx.config.get("reservation_ri_retail_factor", DEFAULT_RI_RETAIL_FACTOR))
    forecast_default = int(ctx.config.get("reservation_forecast_months", DEFAULT_FORECAST_MONTHS))
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
                    util_error = rsv.get("_utilisation_error")
                    if util_error:
                        reason = "consumption summary call failed"
                        hint = (
                            "The `az consumption reservation summary list` "
                            "call returned an error: "
                            f"{util_error}. Most common cause is the runner "
                            "identity lacking `Reservations Reader` on the "
                            "reservation order, or `Cost Management Reader` "
                            "on the billing scope. Grant one of those and "
                            "re-pull."
                        )
                    else:
                        reason = "no utilisation field in collector payload"
                        hint = (
                            "Re-run the reservations collector after "
                            "ensuring the `reservation` extension is current "
                            "(`az extension update --name reservation`); "
                            "some API versions hide utilisation in a "
                            "different property."
                        )
                    findings.append(
                        Finding(
                            **base,
                            title=f"Reservation utilisation unknown: {rsv_name}",
                            severity=Severity.INFO,
                            confidence=Confidence.HIGH,
                            evidence={
                                "sku": sku_name,
                                "reason": reason,
                                **({"error": util_error} if util_error else {}),
                            },
                            recommended_investigation=hint,
                        )
                    )
                    continue
                if util >= threshold:
                    continue
                quantity = int(
                    rsv_props.get("quantity")
                    or rsv_props.get("originalQuantity")
                    or (rsv.get("sku") or {}).get("capacity")
                    or 1
                )
                band = _vm_ri_savings_band(sku_name, util, quantity, ri_factor)
                term_months, term_source = _term_remaining_months(
                    rsv_props, forecast_default
                )
                forecast_low_gbp: float | None = None
                forecast_high_gbp: float | None = None
                if band is not None and term_months > 0:
                    forecast_low_gbp = round(
                        float(band.low_gbp_per_month) * term_months, 2
                    )
                    forecast_high_gbp = round(
                        float(band.high_gbp_per_month) * term_months, 2
                    )
                findings.append(
                    Finding(
                        **base,
                        title=(
                            f"Underused reservation ({util:.1f}% over 30d, "
                            f"target ≥{threshold:.0f}%): {rsv_name}"
                        ),
                        severity=Severity.MEDIUM,
                        confidence=Confidence.MEDIUM,
                        estimated_savings=band,
                        evidence={
                            "utilisation_pct": util,
                            "threshold_pct": threshold,
                            "sku": sku_name,
                            "quantity": quantity,
                            "term_remaining_months": term_months,
                            "term_source": term_source,
                            "forecast_low_gbp_to_expiry": forecast_low_gbp,
                            "forecast_high_gbp_to_expiry": forecast_high_gbp,
                        },
                        recommended_investigation=(
                            "Threshold is FinOps Foundation guidance, not a "
                            "Microsoft-published number. Confirm with the "
                            "reservation owner whether the under-utilisation "
                            "is expected (e.g. workload not yet migrated) or "
                            "if the scope/SKU should be adjusted. The 30-day "
                            "monthly band is a snapshot — the realised £ "
                            f"between now and reservation expiry "
                            f"({term_months} month(s), source: {term_source}) "
                            "is the monthly band × term_remaining_months "
                            "(see evidence.forecast_*_gbp_to_expiry). "
                            "Microsoft permits one exchange or refund per "
                            "reservation order; the £ band is an upper bound "
                            "on what exchange/refund could recover, not a "
                            "guaranteed saving."
                        ),
                    )
                )
    return findings
