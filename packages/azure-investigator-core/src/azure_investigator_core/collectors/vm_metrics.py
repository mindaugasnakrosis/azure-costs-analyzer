"""Per-VM CPU metrics over a 14-day window.

Output shape: list of `{vm_id, vm_name, region, metrics: <az response>}` so
rule code can pivot per VM without a second lookup. Failures for individual
VMs are recorded inline; a whole-collector failure is only emitted when the
prerequisite `vm list` cannot be obtained.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

from . import CollectorOutput, safe_run_json

NAME = "vm_metrics"

WINDOW_DAYS = 14
METRIC_NAME = "Percentage CPU"


def collect(subscription_id: str) -> CollectorOutput:
    vms = safe_run_json(["vm", "list", "--subscription", subscription_id])
    if vms.error or vms.data is None:
        return vms

    end = datetime.now(UTC)
    start = end - timedelta(days=WINDOW_DAYS)
    start_iso = start.strftime("%Y-%m-%dT%H:%M:%SZ")
    end_iso = end.strftime("%Y-%m-%dT%H:%M:%SZ")

    out: list[dict] = []
    for vm in vms.data:
        vm_id = vm.get("id")
        if not vm_id:
            continue
        metrics = safe_run_json(
            [
                "monitor",
                "metrics",
                "list",
                "--resource",
                vm_id,
                "--metric",
                METRIC_NAME,
                "--interval",
                "PT1H",
                "--aggregation",
                "Average",
                "--start-time",
                start_iso,
                "--end-time",
                end_iso,
                "--subscription",
                subscription_id,
            ],
            timeout=180.0,
        )
        out.append(
            {
                "vm_id": vm_id,
                "vm_name": vm.get("name"),
                "region": vm.get("location"),
                "window_start": start_iso,
                "window_end": end_iso,
                "metrics": metrics.data if metrics.data is not None else None,
                "error": metrics.error,
            }
        )
    return CollectorOutput.ok(out)
