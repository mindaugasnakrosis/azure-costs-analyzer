"""Recovery Services Vaults — vault metadata + per-vault backup policies.

Backup retention bloat (60 monthly + 10 yearly recovery points) and GRS
redundancy on non-production data are two of the largest-single-line
cost optimisations available without changing workload behaviour. The
rule layer reads this collector to flag both.

We list vaults at the subscription level, then call `az backup policy
list` per vault to get the retention schedules. Per-item enumeration is
deliberately skipped — it is O(items) calls and only adds the source
size, which the rule layer reconstructs from the consumption snapshot
instead.
"""

from __future__ import annotations

from . import CollectorOutput, safe_run_json

NAME = "recovery_services"


def collect(subscription_id: str) -> CollectorOutput:
    out = safe_run_json(
        ["backup", "vault", "list", "--subscription", subscription_id],
        timeout=180.0,
    )
    if out.error:
        return out
    vaults = out.data if isinstance(out.data, list) else []
    enriched: list[dict] = []
    for vault in vaults:
        if not isinstance(vault, dict):
            continue
        record = dict(vault)
        rg = _resource_group(vault)
        name = vault.get("name")
        # `az backup vault list` historically omits the storage redundancy
        # field on some CLI versions — re-issue `az backup vault backup-
        # properties show` per vault, which surfaces `storageType` directly.
        if rg and name:
            props_out = safe_run_json(
                [
                    "backup",
                    "vault",
                    "backup-properties",
                    "show",
                    "--subscription",
                    subscription_id,
                    "--name",
                    name,
                    "--resource-group",
                    rg,
                ],
                timeout=60.0,
            )
            if not props_out.error:
                # The CLI returns a list of two configs:
                # - vaultstorageconfig (storageType, crossRegionRestoreFlag)
                # - vaultconfig (softDeleteFeatureState, retention, …)
                # Merge both into a single flat dict for the rule layer.
                merged: dict = {}
                items = props_out.data
                if isinstance(items, dict):
                    items = [items]
                if isinstance(items, list):
                    for item in items:
                        if isinstance(item, dict):
                            inner = item.get("properties") or {}
                            if isinstance(inner, dict):
                                # Preserve real values across records — the
                                # vaultstorageconfig record carries
                                # storageType, the vaultconfig record carries
                                # softDeleteFeatureState; each leaves the
                                # other's fields as null. A naive .update()
                                # would clobber the live values with nulls.
                                for k, v in inner.items():
                                    if v is not None or k not in merged:
                                        merged[k] = v
                if merged:
                    record["backup_properties"] = merged
            elif props_out.error:
                record["_backup_properties_error"] = props_out.error
        if rg and name:
            policies_out = safe_run_json(
                [
                    "backup",
                    "policy",
                    "list",
                    "--subscription",
                    subscription_id,
                    "--vault-name",
                    name,
                    "--resource-group",
                    rg,
                ],
                timeout=120.0,
            )
            if policies_out.error:
                record["_policies_error"] = policies_out.error
                record["policies"] = None
            else:
                record["policies"] = policies_out.data or []
        else:
            record["policies"] = []
        enriched.append(record)
    return CollectorOutput.ok(enriched)


def _resource_group(vault: dict) -> str | None:
    rg = vault.get("resourceGroup")
    if rg:
        return rg
    rid = vault.get("id") or ""
    parts = rid.split("/")
    try:
        idx = parts.index("resourceGroups")
    except ValueError:
        try:
            idx = parts.index("resourcegroups")
        except ValueError:
            return None
    if idx + 1 < len(parts):
        return parts[idx + 1]
    return None
