"""Log Analytics workspace metadata.

Lists every workspace in the subscription with its SKU, retention,
daily-cap configuration, and feature flags. The rule layer reads this to
flag oversized retention and legacy SKUs.

We deliberately do *not* run a Log Analytics query API call (`Usage`
table) here: it requires the `log-analytics` extension and per-workspace
read permissions on the data plane, which often differs from the ARM
Reader role that the rest of the snapshot relies on. Per-workspace
ingestion volume is reconstructed at the rule layer from the consumption
collector instead.
"""

from __future__ import annotations

from . import CollectorOutput, safe_run_json

NAME = "log_analytics"


def collect(subscription_id: str) -> CollectorOutput:
    out = safe_run_json(
        ["monitor", "log-analytics", "workspace", "list", "--subscription", subscription_id],
        timeout=180.0,
    )
    if out.error or out.data is None:
        return out
    workspaces = out.data if isinstance(out.data, list) else []
    return CollectorOutput.ok(workspaces)
