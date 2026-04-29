"""SQL servers + databases. Two-step: enumerate servers, then list dbs per server.

Output shape: `{servers: [...], databases: [{server_name, resource_group, dbs: [...]}]}`
to keep the original Azure JSON intact while pre-joining the hierarchy.
"""

from __future__ import annotations

from . import CollectorOutput, safe_run_json

NAME = "sql"


def collect(subscription_id: str) -> CollectorOutput:
    servers = safe_run_json(["sql", "server", "list", "--subscription", subscription_id])
    if servers.error or servers.data is None:
        return servers

    databases: list[dict] = []
    for s in servers.data:
        name = s.get("name")
        rg = s.get("resourceGroup") or s.get("resource_group")
        if not name or not rg:
            continue
        dbs = safe_run_json(
            [
                "sql",
                "db",
                "list",
                "--server",
                name,
                "--resource-group",
                rg,
                "--subscription",
                subscription_id,
            ]
        )
        databases.append(
            {
                "server_name": name,
                "resource_group": rg,
                "dbs": dbs.data if dbs.data is not None else [],
                "error": dbs.error,
            }
        )
    return CollectorOutput.ok({"servers": servers.data, "databases": databases})
