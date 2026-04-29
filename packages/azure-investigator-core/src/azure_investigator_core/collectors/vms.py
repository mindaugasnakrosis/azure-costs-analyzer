"""Virtual machines including instance view (power state).

`-d` (`--show-details`) joins the instance view, giving each VM a `powerState`
field that downstream rules use to detect stopped-but-not-deallocated VMs.
"""

from __future__ import annotations

from . import CollectorOutput, safe_run_json

NAME = "vms"


def collect(subscription_id: str) -> CollectorOutput:
    return safe_run_json(["vm", "list", "-d", "--subscription", subscription_id])
