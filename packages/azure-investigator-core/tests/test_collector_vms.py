"""Regression tests for the vms collector.

The bug these guard against: `az vm list -d` joins instance view server-side
and aborts the whole listing when any single VM is in a transient state
(observed `(ResourceNotFound)` in production tenants). Downstream VM rules
then go silent. The collector must isolate per-VM detail failures.
"""

from __future__ import annotations

from azure_investigator_core.collectors import CollectorOutput, vms


def _stub(responses):
    calls = iter(responses)

    def fake(args, *, timeout=None):  # noqa: ARG001
        return next(calls)

    return fake


def _vm(vm_id, name, size="Standard_D4s_v5"):
    return {
        "id": vm_id,
        "name": name,
        "hardwareProfile": {"vmSize": size},
    }


def _instance_view(power):
    return CollectorOutput.ok(
        {"instanceView": {"statuses": [{"code": f"PowerState/{power}"}]}}
    )


def test_per_vm_failure_does_not_poison_collection(monkeypatch):
    roster = CollectorOutput.ok([_vm("/vms/a", "a"), _vm("/vms/b", "b")])
    bad_view = CollectorOutput.failed(
        "(ResourceNotFound) The resource 'a' under resource group ... was not found"
    )
    good_view = _instance_view("running")
    monkeypatch.setattr(vms, "safe_run_json", _stub([roster, bad_view, good_view]))

    out = vms.collect("sub-1")
    assert out.error is None
    a, b = out.data
    assert "ResourceNotFound" in a["_powerstate_error"]
    assert a.get("powerState") is None
    assert b["powerState"] == "VM running"


def test_powerstate_uses_friendly_form_for_rule_compatibility(monkeypatch):
    roster = CollectorOutput.ok([_vm("/vms/a", "a")])
    monkeypatch.setattr(
        vms, "safe_run_json", _stub([roster, _instance_view("deallocated")])
    )

    out = vms.collect("sub-1")
    (vm,) = out.data
    # `stopped_not_deallocated_vms` and friends read this exact format.
    assert vm["powerState"] == "VM deallocated"


def test_roster_failure_is_returned_unchanged(monkeypatch):
    monkeypatch.setattr(
        vms,
        "safe_run_json",
        _stub([CollectorOutput.failed("(AuthorizationFailed) cannot list VMs")]),
    )

    out = vms.collect("sub-1")
    assert out.data is None
    assert "AuthorizationFailed" in out.error
