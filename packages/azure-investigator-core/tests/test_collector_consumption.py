"""Regression tests for the consumption collector.

The collector calls the Cost Management Query REST API via `az rest`. The
guarantees these tests lock down:
  - Two queries are issued, one per metric (`ActualCost`, `AmortizedCost`).
  - The columnar wire format (`columns` + `rows`) is flattened into dicts.
  - `nextLink` pagination is followed across pages, switching from POST to GET.
  - A query failure surfaces in the per-metric `_error` slot without
    aborting the other metric.
"""

from __future__ import annotations

from azure_investigator_core.collectors import CollectorOutput, consumption


def _query_payload(rows, *, next_link=None):
    body = {
        "properties": {
            "columns": [
                {"name": "Cost", "type": "Number"},
                {"name": "ResourceId", "type": "String"},
            ],
            "rows": rows,
        }
    }
    if next_link is not None:
        body["properties"]["nextLink"] = next_link
    return CollectorOutput.ok(body)


def _stub(responses):
    calls = iter(responses)

    def fake(args, *, timeout=None):  # noqa: ARG001
        return next(calls)

    return fake


def _is_post(args):
    return "--method" in args and args[args.index("--method") + 1] == "post"


def test_columns_and_rows_are_flattened(monkeypatch):
    actual = _query_payload([[1.5, "/r/a"], [2.0, "/r/b"]])
    amortised = _query_payload([[3.0, "/r/c"]])
    monkeypatch.setattr(consumption, "safe_run_json", _stub([actual, amortised]))

    out = consumption.collect("sub-1")
    assert out.error is None
    assert out.data["actual"] == [
        {"Cost": 1.5, "ResourceId": "/r/a"},
        {"Cost": 2.0, "ResourceId": "/r/b"},
    ]
    assert out.data["amortised"] == [{"Cost": 3.0, "ResourceId": "/r/c"}]
    assert out.data["api"] == "Microsoft.CostManagement/query"


def test_next_link_pagination_is_followed_with_get(monkeypatch):
    seen_args = []

    page_1 = _query_payload(
        [[1.0, "/r/a"]], next_link="https://management.azure.com/.../page2"
    )
    page_2 = _query_payload([[2.0, "/r/b"]])
    amortised = _query_payload([])

    def fake(args, *, timeout=None):  # noqa: ARG001
        seen_args.append(args)
        # First two calls = ActualCost (paginated), third = AmortizedCost.
        if len(seen_args) == 1:
            return page_1
        if len(seen_args) == 2:
            return page_2
        return amortised

    monkeypatch.setattr(consumption, "safe_run_json", fake)

    out = consumption.collect("sub-1")
    assert [r["ResourceId"] for r in out.data["actual"]] == ["/r/a", "/r/b"]
    assert _is_post(seen_args[0])
    # nextLink follow-up uses GET, drops the body.
    assert not _is_post(seen_args[1])
    assert "--body" not in seen_args[1]


def test_one_metric_failure_does_not_break_the_other(monkeypatch):
    actual_ok = _query_payload([[5.0, "/r/x"]])
    amortised_failure = CollectorOutput.failed(
        "(BadRequest) malformed timePeriod"
    )
    monkeypatch.setattr(
        consumption, "safe_run_json", _stub([actual_ok, amortised_failure])
    )

    out = consumption.collect("sub-1")
    assert out.data["actual"] == [{"Cost": 5.0, "ResourceId": "/r/x"}]
    assert out.data["amortised"] == []
    assert "BadRequest" in out.data["amortised_error"]
    assert out.data["actual_error"] is None


def test_query_uses_per_call_timeout_not_a_blanket(monkeypatch):
    seen_timeouts = []

    def fake(args, *, timeout=None):  # noqa: ARG001
        seen_timeouts.append(timeout)
        return _query_payload([])

    monkeypatch.setattr(consumption, "safe_run_json", fake)
    consumption.collect("sub-1")
    assert all(t == consumption.PER_QUERY_TIMEOUT_SECONDS for t in seen_timeouts)
    assert consumption.PER_QUERY_TIMEOUT_SECONDS <= 300.0
