"""azure-cost-investigator CLI.

Verbs: analyse, report, knowledge, schema. No verbs that imply mutation —
that's part of the read-only guarantee.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import typer
import yaml
from azure_investigator_core.config import Config
from azure_investigator_core.knowledge_loader import KnowledgeCorpus
from azure_investigator_core.schema import Finding, Report
from azure_investigator_core.snapshot import paths_for, resolve_snapshot_id
from rich.console import Console
from rich.markdown import Markdown
from rich.table import Table

from . import __version__
from .analyse import KnowledgeRefMissing, analyse_snapshot
from .report import render_markdown, render_yaml

app = typer.Typer(
    no_args_is_help=True,
    add_completion=False,
    help="Read-only Azure cost / FinOps investigator.",
)
knowledge_app = typer.Typer(no_args_is_help=True, help="Knowledge corpus inspection.")
app.add_typer(knowledge_app, name="knowledge")

console = Console()
err_console = Console(stderr=True)

PACKAGE = "azure_cost_investigator"


def _load_corpus() -> KnowledgeCorpus:
    return KnowledgeCorpus.load(PACKAGE)


def _resolve_snapshot_paths(snapshot_id: str):
    cfg = Config.load()
    sid = resolve_snapshot_id(cfg.snapshot_root, snapshot_id)
    return cfg, paths_for(cfg.snapshot_root, sid)


def _write_artefacts(paths, report: Report) -> tuple[Path, Path]:
    md_path = paths.base / "report.md"
    yaml_path = paths.base / "findings.yaml"
    md_path.write_text(render_markdown(report), encoding="utf-8")
    yaml_path.write_text(render_yaml(report), encoding="utf-8")
    return md_path, yaml_path


# ---------------------------------------------------------------------------- #
# version


@app.command()
def version() -> None:
    """Print the installed cost-skill version."""
    console.print(__version__)


# ---------------------------------------------------------------------------- #
# analyse


@app.command()
def analyse(
    snapshot_id: str = typer.Argument(
        "latest", help="Snapshot id, or 'latest' to use the most recent pull."
    ),
    only: list[str] = typer.Option(
        [], "--rule", "-r", help="Restrict to these rule ids (repeatable)."
    ),
    exclude: list[str] = typer.Option(
        [], "--exclude-rule", "-x", help="Skip these rule ids (repeatable)."
    ),
    write: bool = typer.Option(
        True,
        "--write/--no-write",
        help="Write report.md + findings.yaml next to the snapshot manifest.",
    ),
    show: bool = typer.Option(
        True,
        "--show/--no-show",
        help="Render the markdown report to stdout.",
    ),
) -> None:
    """Run the cost rules against a snapshot, render report.md + findings.yaml."""
    cfg, paths = _resolve_snapshot_paths(snapshot_id)
    corpus = _load_corpus()
    if not corpus.docs:
        err_console.print(
            "[red]Knowledge corpus is empty.[/red] Reinstall the cost skill "
            "(`uv sync --all-packages`) so the packaged knowledge/*.md files "
            "are present."
        )
        raise typer.Exit(2)

    try:
        report = analyse_snapshot(
            paths,
            corpus,
            only=only or None,
            exclude=exclude or None,
        )
    except KnowledgeRefMissing as e:
        err_console.print(f"[red]{e}[/red]")
        raise typer.Exit(2) from None

    if write:
        md_path, yaml_path = _write_artefacts(paths, report)
        console.print(f"[green]wrote[/green] {md_path}")
        console.print(f"[green]wrote[/green] {yaml_path}")

    if show:
        # Render through Rich for terminal readability; the file on disk stays
        # plain markdown for downstream consumers.
        console.print(Markdown(render_markdown(report)))


# ---------------------------------------------------------------------------- #
# report — re-render an existing analysis without re-running rules


@app.command()
def report(
    snapshot_id: str = typer.Argument("latest", help="Snapshot id or 'latest'."),
    format: str = typer.Option(
        "md",
        "--format",
        "-f",
        help="Output format: md (markdown) or json (findings array).",
    ),
    output: Path | None = typer.Option(
        None, "--output", "-o", help="Write to file instead of stdout."
    ),
) -> None:
    """Re-render an existing analysis from findings.yaml without re-running rules."""
    cfg, paths = _resolve_snapshot_paths(snapshot_id)
    yaml_path = paths.base / "findings.yaml"
    if not yaml_path.exists():
        err_console.print(
            f"[red]No findings.yaml at {yaml_path}.[/red] Run "
            f"`azure-cost-investigator analyse {paths.snapshot_id}` first."
        )
        raise typer.Exit(2)

    payload = yaml.safe_load(yaml_path.read_text(encoding="utf-8"))
    rep = Report.model_validate(payload)

    if format == "md":
        text = render_markdown(rep)
    elif format == "json":
        text = json.dumps(rep.model_dump(mode="json"), indent=2, default=str)
    else:
        err_console.print(f"[red]Unknown format: {format!r}.[/red] Use md or json.")
        raise typer.Exit(2)

    if output is not None:
        output.write_text(text, encoding="utf-8")
        console.print(f"[green]wrote[/green] {output}")
    elif format == "md":
        console.print(Markdown(text))
    else:
        sys.stdout.write(text)
        sys.stdout.flush()


# ---------------------------------------------------------------------------- #
# knowledge


@knowledge_app.command("list")
def knowledge_list() -> None:
    """List the knowledge corpus shipped with the cost skill."""
    corpus = _load_corpus()
    if not corpus.docs:
        console.print("[yellow]Knowledge corpus is empty.[/yellow]")
        return
    table = Table(title="azure-cost-investigator knowledge corpus")
    table.add_column("File")
    table.add_column("Title")
    table.add_column("Source retrieved")
    table.add_column("Cited by")
    for entry in corpus.manifest():
        if entry["filename"] == "README.md":
            continue
        cited = ", ".join(entry["cited_by"]) if entry["cited_by"] else "—"
        table.add_row(
            entry["filename"],
            entry["title"],
            entry["source_retrieved"] or "—",
            cited,
        )
    console.print(table)


@knowledge_app.command("show")
def knowledge_show(
    filename: str = typer.Argument(..., help="Filename inside the knowledge corpus."),
) -> None:
    """Show a single knowledge document, including its frontmatter."""
    corpus = _load_corpus()
    if not corpus.has(filename):
        err_console.print(f"[red]Not found:[/red] {filename}")
        raise typer.Exit(2)
    doc = corpus.get(filename)
    fm_lines = ["---"]
    for key in ("title", "source_url", "source_retrieved", "source_sha256", "cited_by"):
        if key in doc.frontmatter:
            fm_lines.append(f"{key}: {doc.frontmatter[key]}")
    fm_lines.append("---")
    console.print(Markdown("\n".join(fm_lines) + "\n\n" + doc.body))


# ---------------------------------------------------------------------------- #
# schema


@app.command()
def schema(
    target: str = typer.Argument("finding", help="Schema to print: finding | report."),
) -> None:
    """Print the JSON schema for a cost-investigator data type."""
    if target == "finding":
        out = Finding.model_json_schema()
    elif target == "report":
        out = Report.model_json_schema()
    else:
        err_console.print(f"[red]Unknown schema target:[/red] {target!r}. Use finding or report.")
        raise typer.Exit(2)
    console.print_json(json.dumps(out))


if __name__ == "__main__":
    app()
