"""Last 30 days of consumption (actual + amortised).

Two queries — `usage list` defaults to actual; `--include-meter-details` adds
SKU info that pricing rules use to map a record back to a meter and a unit
price. The amortised view is fetched separately via `--metric AmortizedCost`.
The consumption API can be slow on large subscriptions, so we use a long
per-call timeout and let the orchestrator continue on failure.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

from . import CollectorOutput, safe_run_json

NAME = "consumption"


WINDOW_DAYS = 30
TIMEOUT_SECONDS = 600.0


def _window() -> tuple[str, str]:
    end = datetime.now(UTC).date()
    start = end - timedelta(days=WINDOW_DAYS)
    return start.isoformat(), end.isoformat()


def collect(subscription_id: str) -> CollectorOutput:
    start, end = _window()
    actual = safe_run_json(
        [
            "consumption",
            "usage",
            "list",
            "--start-date",
            start,
            "--end-date",
            end,
            "--include-meter-details",
            "--subscription",
            subscription_id,
        ],
        timeout=TIMEOUT_SECONDS,
    )
    amortised = safe_run_json(
        [
            "consumption",
            "usage",
            "list",
            "--start-date",
            start,
            "--end-date",
            end,
            "--metric",
            "AmortizedCost",
            "--include-meter-details",
            "--subscription",
            subscription_id,
        ],
        timeout=TIMEOUT_SECONDS,
    )
    return CollectorOutput.ok(
        {
            "window_start": start,
            "window_end": end,
            "actual": actual.data if actual.data is not None else [],
            "amortised": amortised.data if amortised.data is not None else [],
            "actual_error": actual.error,
            "amortised_error": amortised.error,
        }
    )
