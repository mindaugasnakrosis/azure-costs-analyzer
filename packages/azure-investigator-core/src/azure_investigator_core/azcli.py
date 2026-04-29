"""Read-only wrapper around the `az` CLI.

The architectural firewall: this module is the *only* place the rest of the
codebase calls `az`. It refuses any subcommand that begins with a write verb,
even if a future caller passes one in by mistake. The list intentionally errs
on the side of refusal — read-only is absolute.
"""

from __future__ import annotations

import json
import shutil
import subprocess
from collections.abc import Sequence
from dataclasses import dataclass

# Verbs that mutate Azure state. If the *first* token of an `az` invocation OR
# the *last* token (the action verb in `az <noun> <verb>` form) matches any of
# these, the call is refused.
FORBIDDEN_VERBS: frozenset[str] = frozenset(
    {
        "create",
        "update",
        "delete",
        "set",
        "add",
        "remove",
        "assign",
        "unassign",
        "start",
        "stop",
        "restart",
        "deallocate",
        "redeploy",
        "reset",
        "reimage",
        "lock",
        "unlock",
        "import",
        "export-policy",
        "purge",
        "wait",
        "invoke",
        "renew",
        "regenerate",
        "rotate",
        "approve",
        "deny",
        "cancel",
        "publish",
        "deploy",
        "apply",
        "patch",
        "enable",
        "disable",
    }
)

# Subcommand groups that are mutation-only and should be refused even if a
# specific verb token is missing (e.g. `az tag` without a verb is an error,
# but `az tag update ...` would otherwise slip past a naive prefix check).
FORBIDDEN_GROUP_VERB_PAIRS: frozenset[tuple[str, str]] = frozenset(
    {
        ("policy", "assignment"),
        ("role", "assignment"),
        ("tag", "update"),
        ("tag", "create"),
    }
)


class AzCliWriteRefused(RuntimeError):
    """Raised when a write `az` invocation is attempted.

    This is the architectural firewall guaranteeing the read-only contract of
    the azure-investigator family. It is intentionally non-recoverable.
    """


class AzCliError(RuntimeError):
    """Raised on a non-zero exit from `az` for an otherwise-allowed call."""


@dataclass(frozen=True)
class AzResult:
    args: tuple[str, ...]
    returncode: int
    stdout: str
    stderr: str


def _refuse_if_write(args: Sequence[str]) -> None:
    tokens = [a for a in args if not a.startswith("-")]
    if not tokens:
        return

    for tok in tokens:
        if tok in FORBIDDEN_VERBS:
            raise AzCliWriteRefused(
                f"Refusing to run `az {' '.join(args)}` — token {tok!r} is a "
                "write verb. azure-investigator is read-only by architectural "
                "guarantee; no subcommand may mutate Azure state."
            )

    for i in range(len(tokens) - 1):
        pair = (tokens[i], tokens[i + 1])
        if pair in FORBIDDEN_GROUP_VERB_PAIRS:
            raise AzCliWriteRefused(
                f"Refusing to run `az {' '.join(args)}` — "
                f"subcommand pair {pair} is a write operation. "
                "azure-investigator is read-only by architectural guarantee."
            )


def _resolve_az_binary() -> str:
    az = shutil.which("az")
    if not az:
        raise AzCliError(
            "`az` binary not found on PATH. Install the Azure CLI: "
            "https://learn.microsoft.com/cli/azure/install-azure-cli"
        )
    return az


def run(
    args: Sequence[str],
    *,
    check: bool = True,
    timeout: float | None = 120.0,
) -> AzResult:
    """Run `az <args>` with the read-only guard. Returns an AzResult."""
    args = tuple(args)
    _refuse_if_write(args)
    az = _resolve_az_binary()
    proc = subprocess.run(
        [az, *args],
        capture_output=True,
        text=True,
        timeout=timeout,
        check=False,
    )
    result = AzResult(
        args=args,
        returncode=proc.returncode,
        stdout=proc.stdout,
        stderr=proc.stderr,
    )
    if check and result.returncode != 0:
        raise AzCliError(
            f"`az {' '.join(args)}` exited {result.returncode}: "
            f"{(result.stderr or result.stdout).strip()[:500]}"
        )
    return result


def run_json(args: Sequence[str], *, timeout: float | None = 120.0):
    """Run `az ... -o json` and parse the response. Returns parsed JSON or None on empty."""
    args = tuple(args)
    if "-o" not in args and "--output" not in args:
        args = (*args, "-o", "json")
    result = run(args, check=True, timeout=timeout)
    out = result.stdout.strip()
    if not out:
        return None
    return json.loads(out)
