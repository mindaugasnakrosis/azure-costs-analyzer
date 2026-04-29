"""Managed disks. `diskState` and `managedBy` drive orphan detection.

`az disk list` without `--resource-group` is unsupported in some Azure CLI
builds (raises "the following arguments are required: --resource-group/-g").
We enumerate resource groups first and fan out per-RG, which is reliable on
every CLI version.
"""

from __future__ import annotations

from . import CollectorOutput, safe_run_json

NAME = "disks"


def collect(subscription_id: str) -> CollectorOutput:
    groups = safe_run_json(
        [
            "group",
            "list",
            "--subscription",
            subscription_id,
            "--query",
            "[].name",
        ]
    )
    if groups.error or groups.data is None:
        return groups

    all_disks: list[dict] = []
    errors: list[str] = []
    for rg in groups.data:
        out = safe_run_json(
            [
                "disk",
                "list",
                "--resource-group",
                rg,
                "--subscription",
                subscription_id,
            ]
        )
        if out.error:
            errors.append(f"{rg}: {out.error}")
            continue
        if out.data:
            all_disks.extend(out.data)

    # If every per-RG call failed, surface as a collector error so the
    # orphaned_disks rule still emits Info instead of running blind.
    if errors and not all_disks:
        return CollectorOutput.failed(f"all per-resource-group disk listings failed: {errors[0]}")
    return CollectorOutput.ok(all_disks)
