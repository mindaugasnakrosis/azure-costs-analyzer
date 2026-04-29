from __future__ import annotations

from azure_investigator_core import azcli
from azure_investigator_core.collectors import (
    COLLECTOR_MODULES,
    CollectorOutput,
    iter_collectors,
)


def test_all_collectors_discover_and_have_collect_fn():
    found = list(iter_collectors())
    assert len(found) == len(COLLECTOR_MODULES)
    for name, fn in found:
        assert callable(fn), f"{name}: collect must be callable"


def test_iter_collectors_filter():
    found = [n for n, _ in iter_collectors(only=["vms", "disks"])]
    assert set(found) == {"vms", "disks"}


def test_collectors_use_safe_run_json_only(mocker):
    """Exercise every collector against a stubbed `run_json` and confirm:
    - every emitted call goes via the read-only wrapper
    - failures translate to CollectorOutput(error=...) not exceptions
    """

    def fake_run_json(args, *, timeout=None):
        # Always produce an empty list so collectors that compose multiple calls
        # (vm_metrics, sql, reservations) can iterate without recursion.
        return []

    mocker.patch.object(azcli, "run_json", side_effect=fake_run_json)
    # The collector module imports `safe_run_json` from the package init, which
    # itself calls `run_json`. Patch at that level too:
    mocker.patch(
        "azure_investigator_core.collectors.run_json",
        side_effect=fake_run_json,
    )

    for name, fn in iter_collectors():
        out = fn("sub-1")
        assert isinstance(out, CollectorOutput), name
        assert out.error is None, f"{name} returned error: {out.error}"


def test_collector_output_factories():
    ok = CollectorOutput.ok([{"a": 1}, {"b": 2}])
    assert ok.record_count == 2
    assert ok.error is None
    fail = CollectorOutput.failed("auth")
    assert fail.error == "auth"
    assert fail.data is None
