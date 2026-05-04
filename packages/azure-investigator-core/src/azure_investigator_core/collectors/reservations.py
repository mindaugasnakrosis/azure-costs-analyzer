"""Reservation orders + 30-day utilisation summaries.

Reservations are a billing-account-scope resource, not a subscription-scope one.
The `az reservations` extension is required (`az extension add --name reservation`).
We make a best-effort call; if the extension is missing the orchestrator
records an error and the underused-reservations rule downgrades to Info.

Utilisation does not appear in the `az reservations reservation list` payload —
it lives on the Cost Management consumption summary endpoint:
`az consumption reservation summary list --grain monthly`. We fetch that per
order over the last ~30 days and merge `avgUtilizationPercentage` onto each
reservation record so the rule can read a single property.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

from . import CollectorOutput, safe_run_json

NAME = "reservations"

# Cost Management's reservation-summary window. 30 days is the FinOps
# Foundation default for utilisation review.
SUMMARY_WINDOW_DAYS = 30


def _summary_window() -> tuple[str, str]:
    end = datetime.now(UTC).date()
    start = end - timedelta(days=SUMMARY_WINDOW_DAYS)
    return start.isoformat(), end.isoformat()


def _index_summary(records: list[dict]) -> dict[str, dict]:
    """Index a `consumption reservation summary list` payload by reservation ID.

    The payload may contain more than one row per reservation when the 30-day
    window straddles a month boundary (`--grain monthly`). Keep the row with
    the most recent `usageDate` so we report the latest known utilisation.
    """
    out: dict[str, dict] = {}
    for r in records or []:
        rsv_id = r.get("reservationId") or r.get("name")
        if not rsv_id:
            continue
        existing = out.get(rsv_id)
        if existing is None or str(r.get("usageDate", "")) > str(existing.get("usageDate", "")):
            out[rsv_id] = r
    return out


def _leaf(value: str | None) -> str | None:
    """Return the trailing path segment.

    `az reservations reservation list` returns `name = "{orderGuid}/{rsvGuid}"`
    and `id = ".../reservations/{rsvGuid}"`, while
    `az consumption reservation summary list` returns `reservationId = "{rsvGuid}"`.
    Strip everything before the last '/' so the two surfaces match.
    """
    if not value:
        return None
    return value.rsplit("/", 1)[-1] or None


def collect(subscription_id: str) -> CollectorOutput:
    orders = safe_run_json(["reservations", "reservation-order", "list"], timeout=300.0)
    if orders.error or orders.data is None:
        return orders

    start, end = _summary_window()
    detailed: list[dict] = []
    for order in orders.data:
        order_id = order.get("id", "").split("/")[-1] or order.get("name")
        if not order_id:
            continue
        rsvs = safe_run_json(
            ["reservations", "reservation", "list", "--reservation-order-id", order_id],
            timeout=180.0,
        )
        summary = safe_run_json(
            [
                "consumption",
                "reservation",
                "summary",
                "list",
                "--grain",
                "monthly",
                "--reservation-order-id",
                order_id,
                "--start-date",
                start,
                "--end-date",
                end,
            ],
            timeout=180.0,
        )
        summary_index = _index_summary(summary.data or [])

        # Merge utilisation onto each reservation record so the rule can read
        # a single property (`avgUtilizationPercentage`) without reaching for
        # a sibling list. Match on the leaf reservation GUID — the two az
        # surfaces disagree on how they format the identifier (see _leaf).
        merged_reservations: list[dict] = []
        for rsv in rsvs.data or []:
            rsv_id = _leaf(rsv.get("name")) or _leaf(rsv.get("id"))
            entry = summary_index.get(rsv_id) if rsv_id else None
            merged = dict(rsv)
            if entry:
                merged["summary"] = entry
                merged["avgUtilizationPercentage"] = entry.get("avgUtilizationPercentage")
            elif summary.error:
                # Surface the consumption call's failure reason so the rule
                # can distinguish "API unreachable" from "ID didn't match".
                merged["_utilisation_error"] = summary.error
            merged_reservations.append(merged)

        detailed.append(
            {
                "order": order,
                "reservations": merged_reservations,
                "summary_window_start": start,
                "summary_window_end": end,
                "error": rsvs.error,
                "summary_error": summary.error,
            }
        )
    return CollectorOutput.ok(detailed)
