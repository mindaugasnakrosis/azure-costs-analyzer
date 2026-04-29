"""azure-investigator core CLI.

Verbs: init, doctor, pull, snapshot ls/show, schema. No write verbs — by
deliberate naming. Both skills (cost, security) reuse `pull` and `snapshot`.
"""

from __future__ import annotations

import json
import shutil
from pathlib import Path

import typer
import yaml
from rich.console import Console
from rich.table import Table

from . import __version__
from .azcli import AzCliError, AzCliWriteRefused, run_json
from .config import Config, default_config_path
from .knowledge_loader import KnowledgeCorpus
from .pull import pull as pull_run
from .schema import Finding, SnapshotManifest
from .snapshot import (
    list_snapshots,
    paths_for,
    read_manifest,
    resolve_snapshot_id,
)

app = typer.Typer(
    no_args_is_help=True,
    add_completion=False,
    help="Read-only Azure investigator core: auth, snapshotting, pricing.",
)
snapshot_app = typer.Typer(no_args_is_help=True, help="Snapshot inspection commands.")
app.add_typer(snapshot_app, name="snapshot")

console = Console()
err_console = Console(stderr=True)


@app.command()
def version() -> None:
    """Print the installed core version."""
    console.print(__version__)


@app.command()
def init(
    config_path: Path | None = typer.Option(
        None, "--config", help="Override config path (default: platform user config dir)."
    ),
) -> None:
    """Interactive setup: verify `az login`, discover subscriptions, write config."""
    target = config_path or default_config_path()
    if shutil.which("az") is None:
        err_console.print(
            "[red]Azure CLI not found.[/red] Install: "
            "https://learn.microsoft.com/cli/azure/install-azure-cli"
        )
        raise typer.Exit(2)

    try:
        identity = run_json(["account", "show"])
    except AzCliError:
        identity = None

    if identity is None:
        console.print("Not logged in. Run [bold]az login[/bold] first.")
        raise typer.Exit(2)

    user = (identity.get("user") or {}).get("name") or "unknown"
    console.print(f"Signed in as [bold]{user}[/bold]")

    try:
        accounts = run_json(["account", "list", "--refresh"]) or []
    except AzCliError as e:
        err_console.print(f"[red]Failed to list subscriptions:[/red] {e}")
        raise typer.Exit(2) from None

    table = Table(title="Subscriptions visible to this identity")
    table.add_column("Name")
    table.add_column("Id")
    table.add_column("State")
    for a in accounts:
        table.add_row(a.get("name", ""), a.get("id", ""), a.get("state", ""))
    console.print(table)

    cfg = Config()
    target.parent.mkdir(parents=True, exist_ok=True)
    cfg.write(target)
    console.print(f"Wrote config → {target}")


@app.command()
def doctor() -> None:
    """Verify environment readiness: az present, logged in, subscriptions accessible,
    and that each known skill's knowledge corpus loads cleanly."""
    rc = 0
    if shutil.which("az") is None:
        err_console.print("[red]✗[/red] az CLI not on PATH")
        rc = 1
    else:
        console.print("[green]✓[/green] az CLI present")

    try:
        ident = run_json(["account", "show"])
        user = (ident.get("user") or {}).get("name", "unknown") if ident else "unknown"
        console.print(f"[green]✓[/green] az login active ({user})")
    except (AzCliError, AzCliWriteRefused) as e:
        err_console.print(f"[red]✗[/red] az login: {e}")
        rc = 1

    try:
        subs = run_json(["account", "list"]) or []
        console.print(f"[green]✓[/green] {len(subs)} subscription(s) visible")
    except AzCliError as e:
        err_console.print(f"[red]✗[/red] subscription list: {e}")
        rc = 1

    for pkg in ("azure_cost_investigator", "azure_security_investigator"):
        corpus = KnowledgeCorpus.load(pkg)
        if corpus.docs:
            console.print(f"[green]✓[/green] knowledge corpus {pkg}: {len(corpus.docs)} docs")
        else:
            console.print(
                f"[yellow]·[/yellow] knowledge corpus {pkg}: empty (expected pre-authoring)"
            )

    raise typer.Exit(rc)


@app.command()
def pull(
    subscription: list[str] = typer.Option(
        [], "--subscription", "-s", help="Subscription id or name to include (repeatable)."
    ),
    exclude: list[str] = typer.Option(
        [], "--exclude", "-x", help="Subscription id or name to exclude (repeatable)."
    ),
    collectors: list[str] = typer.Option(
        [], "--collector", "-c", help="Restrict to these collector names (repeatable)."
    ),
) -> None:
    """Run a snapshot against the selected subscriptions × collectors."""
    cfg = Config.load()
    paths = pull_run(
        config=cfg,
        subscriptions=subscription or None,
        exclude=exclude or [],
        collectors=collectors or None,
        progress=console.print,
    )
    console.print(f"\nSnapshot id: [bold]{paths.snapshot_id}[/bold]")


@snapshot_app.command("ls")
def snapshot_ls() -> None:
    """List snapshots in the configured snapshot root."""
    cfg = Config.load()
    snaps = list_snapshots(cfg.snapshot_root)
    if not snaps:
        console.print(f"No snapshots under {cfg.snapshot_root}.")
        return
    table = Table(title=str(cfg.snapshot_root))
    table.add_column("Snapshot id")
    table.add_column("Subscriptions")
    table.add_column("OK collectors")
    table.add_column("Errors")
    for sid in snaps:
        try:
            m = read_manifest(paths_for(cfg.snapshot_root, sid))
        except Exception as e:  # noqa: BLE001
            table.add_row(sid, "—", "—", f"[red]manifest error: {e}[/red]")
            continue
        ok = sum(1 for r in m.collector_results if r.status == "ok")
        err = sum(1 for r in m.collector_results if r.status == "error")
        table.add_row(sid, str(len(m.subscriptions)), str(ok), str(err))
    console.print(table)


@snapshot_app.command("show")
def snapshot_show(snapshot_id: str = typer.Argument(..., help="Snapshot id or 'latest'.")) -> None:
    """Show the manifest of a snapshot."""
    cfg = Config.load()
    sid = resolve_snapshot_id(cfg.snapshot_root, snapshot_id)
    m = read_manifest(paths_for(cfg.snapshot_root, sid))
    console.print(yaml.safe_dump(m.model_dump(mode="json"), sort_keys=False))


@app.command()
def schema(target: str = typer.Argument("finding", help="One of: finding, snapshot.")) -> None:
    """Print the JSON schema for a core data type."""
    if target == "finding":
        out = Finding.model_json_schema()
    elif target == "snapshot":
        out = SnapshotManifest.model_json_schema()
    else:
        err_console.print(f"Unknown schema target: {target!r}. Use finding or snapshot.")
        raise typer.Exit(2)
    console.print_json(json.dumps(out))


if __name__ == "__main__":
    app()
