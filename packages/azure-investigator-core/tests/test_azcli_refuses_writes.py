from __future__ import annotations

import pytest
from azure_investigator_core.azcli import (
    FORBIDDEN_VERBS,
    AzCliWriteRefused,
    run,
    run_json,
)

WRITE_INVOCATIONS = [
    ["vm", "deallocate", "--name", "x", "-g", "rg"],
    ["vm", "delete", "--name", "x"],
    ["vm", "create", "--name", "x"],
    ["vm", "update", "--name", "x"],
    ["vm", "start", "--name", "x"],
    ["vm", "stop", "--name", "x"],
    ["vm", "restart", "--name", "x"],
    ["disk", "delete", "--name", "x"],
    ["network", "public-ip", "delete", "--name", "x"],
    ["tag", "update", "--resource-id", "x"],
    ["tag", "create", "--resource-id", "x"],
    ["role", "assignment", "create"],
    ["policy", "assignment", "create"],
    ["lock", "create", "--name", "x"],
    ["resource", "delete", "--ids", "x"],
    ["account", "set", "--subscription", "sub-1"],
    ["group", "create", "--name", "rg"],
    ["storage", "account", "update", "--name", "s"],
    ["sql", "db", "delete", "--name", "x"],
    ["snapshot", "delete", "--name", "x"],
]


@pytest.mark.parametrize("args", WRITE_INVOCATIONS)
def test_write_invocations_refused(args):
    with pytest.raises(AzCliWriteRefused):
        run(args)


def test_run_json_also_refused_for_writes():
    with pytest.raises(AzCliWriteRefused):
        run_json(["vm", "delete", "--name", "x"])


def test_forbidden_verbs_covers_pe_audit_minimum():
    must_block = {
        "create",
        "update",
        "delete",
        "set",
        "add",
        "remove",
        "assign",
        "start",
        "stop",
        "restart",
        "deallocate",
    }
    assert must_block <= FORBIDDEN_VERBS


def test_read_invocation_passes_guard(mocker):
    mocker.patch("azure_investigator_core.azcli._resolve_az_binary", return_value="/usr/bin/az")
    mock_run = mocker.patch(
        "azure_investigator_core.azcli.subprocess.run",
        return_value=mocker.Mock(returncode=0, stdout="[]", stderr=""),
    )
    result = run_json(["vm", "list"])
    assert result == []
    called_args = mock_run.call_args.args[0]
    assert called_args[1:] == ["vm", "list", "-o", "json"]
