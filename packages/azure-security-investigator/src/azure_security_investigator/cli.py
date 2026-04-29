"""azure-security-investigator — v2 stub.

The security-persona companion to azure-cost-investigator. Reserves the
namespace and the `analyse` verb shape so v1 consumers can't accidentally
take a dependency on a sibling skill that doesn't yet exist.
"""

from __future__ import annotations

import typer
from rich.console import Console

from . import __version__

app = typer.Typer(
    no_args_is_help=False,
    add_completion=False,
    help="Reserved namespace — security-persona skill ships in v2.",
)
console = Console()
err_console = Console(stderr=True)


@app.command()
def version() -> None:
    """Print the stub version (always 0.0.0 in v1)."""
    console.print(__version__)


@app.command()
def analyse(
    snapshot_id: str = typer.Argument(
        "latest", help="Reserved — accepted for forward compatibility."
    ),
) -> None:
    """v2 — not yet implemented."""
    err_console.print(
        "[yellow]azure-security-investigator is a v2 stub.[/yellow] "
        "Use [bold]azure-cost-investigator[/bold] for v1 cost reviews; the "
        "security skill ships next."
    )
    raise typer.Exit(2)


if __name__ == "__main__":
    app()
