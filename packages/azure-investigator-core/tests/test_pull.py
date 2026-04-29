from __future__ import annotations

import json

from azure_investigator_core import pull as pull_mod
from azure_investigator_core.collectors import CollectorOutput
from azure_investigator_core.config import Config
from azure_investigator_core.schema import SubscriptionRef
from azure_investigator_core.snapshot import read_manifest


def _stub_subs():
    return [
        SubscriptionRef(id="sub-1", name="TEST", tenant_id="t1", state="Enabled"),
        SubscriptionRef(id="sub-2", name="PROD", tenant_id="t1", state="Enabled"),
    ]


def test_pull_writes_manifest_and_collector_payloads(tmp_path, mocker):
    cfg = Config(snapshot_root=tmp_path / "snaps", price_cache_root=tmp_path / "cache")

    mocker.patch.object(pull_mod, "_identity", return_value="me@example.com")
    mocker.patch.object(pull_mod, "_list_subscriptions", return_value=_stub_subs())

    def fake_iter(only=None):
        # Two collectors: one succeeds, one fails. The failing one should not abort the run.
        def ok_collect(sub_id):
            return CollectorOutput.ok([{"id": f"r-{sub_id}-1"}])

        def bad_collect(sub_id):
            return CollectorOutput.failed("permission denied")

        yield "vms", ok_collect
        yield "disks", bad_collect

    mocker.patch.object(pull_mod, "iter_collectors", fake_iter)

    paths = pull_mod.pull(config=cfg)

    # manifest exists and lists both collectors as run, even though disks failed
    manifest = read_manifest(paths)
    assert manifest.collectors_run == ["vms", "disks"]
    assert {(r.collector, r.subscription_id, r.status) for r in manifest.collector_results} == {
        ("vms", "sub-1", "ok"),
        ("disks", "sub-1", "error"),
        ("vms", "sub-2", "ok"),
        ("disks", "sub-2", "error"),
    }

    # successful payloads are on disk
    assert (paths.subscription_dir("sub-1") / "vms.json").exists()
    assert (paths.subscription_dir("sub-2") / "vms.json").exists()
    # failures have no payload, but show up in collector_errors.json
    assert not (paths.subscription_dir("sub-1") / "disks.json").exists()
    errs = json.loads(paths.collector_errors_path("sub-1").read_text())
    assert len(errs) == 1
    assert errs[0]["collector"] == "disks"


def test_pull_continues_when_collector_raises(tmp_path, mocker):
    cfg = Config(snapshot_root=tmp_path / "snaps", price_cache_root=tmp_path / "cache")
    mocker.patch.object(pull_mod, "_identity", return_value="me@example.com")
    mocker.patch.object(pull_mod, "_list_subscriptions", return_value=_stub_subs()[:1])

    def fake_iter(only=None):
        def boom(sub_id):
            raise RuntimeError("boom")

        def ok(sub_id):
            return CollectorOutput.ok([])

        yield "broken", boom
        yield "ok", ok

    mocker.patch.object(pull_mod, "iter_collectors", fake_iter)
    paths = pull_mod.pull(config=cfg)
    manifest = read_manifest(paths)
    statuses = {(r.collector, r.status): r for r in manifest.collector_results}
    assert statuses[("broken", "error")].error.startswith("RuntimeError")
    assert statuses[("ok", "ok")].record_count == 0
