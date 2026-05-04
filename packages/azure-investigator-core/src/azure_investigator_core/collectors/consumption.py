"""Last 30 days of consumption (actual + amortised) via Cost Management Query.

We previously called `az consumption usage list`, which streams raw line
items from the legacy Cost Management API. On large subscriptions a single
call hung past any reasonable timeout — observed indefinitely on a
£20k/mo tenant — and even after slicing the window into 7-day chunks the
per-slice payload (with `--include-meter-details`) didn't return.

Instead we hit the modern Cost Management Query REST API:
`POST /subscriptions/{id}/providers/Microsoft.CostManagement/query`. It
aggregates server-side and returns dramatically smaller, faster responses
(seconds instead of indefinite hangs). We call it via `az rest`, which
keeps the read-only firewall in `azcli.py` in force — POST is the
endpoint's contract for queries because of body size, not because the
endpoint mutates state.

Two metrics are queried (`ActualCost`, `AmortizedCost`), each grouped by
ResourceId/ServiceName/MeterCategory/ChargeType so downstream rules can
ground cost bands in invoiced spend per resource. We follow `nextLink`
pagination so large subscriptions don't drop rows.
"""

from __future__ import annotations

import json
from datetime import UTC, date, datetime, timedelta

from . import CollectorOutput, safe_run_json

NAME = "consumption"

WINDOW_DAYS = 30
PER_QUERY_TIMEOUT_SECONDS = 180.0
API_VERSION = "2023-11-01"
MAX_PAGES = 50  # safety belt; one tenant returning >50 pages is a smell, not a feature.


def _window() -> tuple[date, date]:
    end = datetime.now(UTC).date()
    start = end - timedelta(days=WINDOW_DAYS)
    return start, end


def _query_body(metric: str, start: date, end: date) -> dict:
    """Cost Management Query payload — daily granularity, grouped per-resource.

    `metric` must be one of `ActualCost`, `AmortizedCost`. The grouping
    dimensions are chosen so rules can roll up by service/category/charge
    type without re-querying.
    """
    return {
        "type": metric,
        "timeframe": "Custom",
        "timePeriod": {
            "from": f"{start.isoformat()}T00:00:00+00:00",
            "to": f"{end.isoformat()}T23:59:59+00:00",
        },
        "dataset": {
            "granularity": "Daily",
            "aggregation": {"totalCost": {"name": "Cost", "function": "Sum"}},
            "grouping": [
                {"type": "Dimension", "name": "ResourceId"},
                {"type": "Dimension", "name": "ServiceName"},
                {"type": "Dimension", "name": "MeterCategory"},
                {"type": "Dimension", "name": "ChargeType"},
            ],
        },
    }


def _rows_to_records(payload: object) -> list[dict]:
    """Cost Management returns columns + rows; flatten to a list of dicts.

    Empty / unexpected payloads just produce []. Callers shouldn't have to
    know about the columnar wire format, and shouldn't crash if a stub or
    a degraded API returns something other than the expected dict shape.
    """
    if not isinstance(payload, dict):
        return []
    props = payload.get("properties") or {}
    columns = [c.get("name") for c in props.get("columns") or []]
    rows = props.get("rows") or []
    return [dict(zip(columns, row, strict=False)) for row in rows]


def _next_link(payload: object) -> str | None:
    if not isinstance(payload, dict):
        return None
    props = payload.get("properties") or {}
    return props.get("nextLink") or payload.get("nextLink")


def _query_metric(
    subscription_id: str,
    *,
    metric: str,
    start: date,
    end: date,
) -> tuple[list[dict], str | None]:
    """Run one Cost Management Query, following pagination. Returns (records, error)."""
    base_uri = (
        f"https://management.azure.com/subscriptions/{subscription_id}"
        f"/providers/Microsoft.CostManagement/query?api-version={API_VERSION}"
    )
    body = json.dumps(_query_body(metric, start, end))
    records: list[dict] = []
    uri = base_uri
    method = "post"
    for _ in range(MAX_PAGES):
        args = [
            "rest",
            "--method",
            method,
            "--uri",
            uri,
            "--headers",
            "Content-Type=application/json",
        ]
        # nextLink continues with GET and no body.
        if method == "post":
            args.extend(["--body", body])
        out = safe_run_json(args, timeout=PER_QUERY_TIMEOUT_SECONDS)
        if out.error or out.data is None:
            return records, out.error
        records.extend(_rows_to_records(out.data))
        nxt = _next_link(out.data)
        if not nxt:
            return records, None
        uri = nxt
        method = "get"
    return records, f"Cost Management query exceeded {MAX_PAGES} pages of pagination"


def collect(subscription_id: str) -> CollectorOutput:
    start, end = _window()
    actual, actual_error = _query_metric(
        subscription_id, metric="ActualCost", start=start, end=end
    )
    amortised, amortised_error = _query_metric(
        subscription_id, metric="AmortizedCost", start=start, end=end
    )
    return CollectorOutput.ok(
        {
            "window_start": start.isoformat(),
            "window_end": end.isoformat(),
            "api": "Microsoft.CostManagement/query",
            "api_version": API_VERSION,
            "actual": actual,
            "amortised": amortised,
            "actual_error": actual_error,
            "amortised_error": amortised_error,
        }
    )
