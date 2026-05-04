"""Virtual machines + per-VM power state.

We previously used `az vm list -d`, which joins the instance view server-side.
That single call aborts the whole listing if any one VM is in a transient
state (e.g. mid-delete) — the entire collector errors out and downstream
rules go silent.

Instead we fetch the bulk roster with plain `az vm list`, then attach a
power-state to each VM via a per-VM `az vm get-instance-view` call. A
per-VM failure is captured on that VM's record (`_powerstate_error`) but
does not poison the rest of the collection.

Downstream rules read `powerState` as the friendly string Azure CLI uses
with `-d` (e.g. `"VM running"`, `"VM deallocated"`); we reconstruct that
form from the instance-view `statuses[].code` so existing rule logic keeps
working unchanged.
"""

from __future__ import annotations

from . import CollectorOutput, safe_run_json

NAME = "vms"


def _power_state_from_statuses(statuses: list[dict] | None) -> str | None:
    """Derive `"VM <state>"` from an instance-view statuses array.

    statuses look like `[{"code": "PowerState/running", ...}, ...]`. Returning
    `None` when no PowerState code is present matches what `az vm list -d`
    does for VMs whose instance view is unreachable.
    """
    for s in statuses or []:
        code = s.get("code") or ""
        if code.startswith("PowerState/"):
            return f"VM {code.split('/', 1)[1]}"
    return None


def collect(subscription_id: str) -> CollectorOutput:
    roster = safe_run_json(["vm", "list", "--subscription", subscription_id])
    if roster.error or roster.data is None:
        return roster

    enriched: list[dict] = []
    for vm in roster.data:
        vm_id = vm.get("id")
        record = dict(vm)
        if not vm_id:
            enriched.append(record)
            continue
        view = safe_run_json(
            ["vm", "get-instance-view", "--ids", vm_id],
            timeout=60.0,
        )
        if view.error or view.data is None:
            record["_powerstate_error"] = view.error or "no instance view returned"
        else:
            statuses = (view.data.get("instanceView") or {}).get("statuses")
            record["powerState"] = _power_state_from_statuses(statuses)
            record["instanceView"] = view.data.get("instanceView")
        enriched.append(record)
    return CollectorOutput.ok(enriched)
