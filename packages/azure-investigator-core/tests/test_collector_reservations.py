"""Regression tests for the reservations collector.

The bug these guard against: `az reservations reservation list` returns
`name = "{orderGuid}/{rsvGuid}"`, while
`az consumption reservation summary list` returns `reservationId = "{rsvGuid}"`.
The collector must reconcile the two so utilisation actually merges onto the
reservation record. Before the fix, every reservation showed up with
`avgUtilizationPercentage = None` and the rule emitted Info for all of them.
"""

from __future__ import annotations

from azure_investigator_core.collectors import CollectorOutput, reservations


def _stub_run_json(responses):
    """Build a fake `safe_run_json` that returns canned outputs in call order."""
    calls = iter(responses)

    def fake(args, *, timeout=None):  # noqa: ARG001
        return next(calls)

    return fake


ORDER_ID = "00000000-0000-0000-0000-000000000001"
RSV_GUID = "11111111-1111-1111-1111-111111111111"


def _orders_response():
    return CollectorOutput.ok(
        [{"id": f"/providers/Microsoft.Capacity/reservationOrders/{ORDER_ID}"}]
    )


def _reservations_response():
    # Note the composite `name` — this is what tripped the original code up.
    return CollectorOutput.ok(
        [
            {
                "id": (
                    f"/providers/Microsoft.Capacity/reservationOrders/{ORDER_ID}"
                    f"/reservations/{RSV_GUID}"
                ),
                "name": f"{ORDER_ID}/{RSV_GUID}",
                "sku": {"name": "Standard_D4s_v5"},
                "properties": {"displayName": "vm-fleet-ri"},
            }
        ]
    )


def test_utilisation_merges_when_name_is_composite(monkeypatch):
    summary = CollectorOutput.ok(
        [
            {
                "reservationId": RSV_GUID,
                "avgUtilizationPercentage": 73.4,
                "usageDate": "2026-04-01",
            }
        ]
    )
    monkeypatch.setattr(
        reservations,
        "safe_run_json",
        _stub_run_json([_orders_response(), _reservations_response(), summary]),
    )

    out = reservations.collect("sub-1")
    assert out.error is None
    (entry,) = out.data
    (rsv,) = entry["reservations"]
    assert rsv["avgUtilizationPercentage"] == 73.4
    assert rsv["summary"]["usageDate"] == "2026-04-01"


def test_latest_monthly_bucket_wins_when_window_straddles_boundary(monkeypatch):
    # 30-day window can return two monthly rows; the most recent should win.
    summary = CollectorOutput.ok(
        [
            {
                "reservationId": RSV_GUID,
                "avgUtilizationPercentage": 40.0,
                "usageDate": "2026-03-01",
            },
            {
                "reservationId": RSV_GUID,
                "avgUtilizationPercentage": 91.5,
                "usageDate": "2026-04-01",
            },
        ]
    )
    monkeypatch.setattr(
        reservations,
        "safe_run_json",
        _stub_run_json([_orders_response(), _reservations_response(), summary]),
    )

    out = reservations.collect("sub-1")
    (rsv,) = out.data[0]["reservations"]
    assert rsv["avgUtilizationPercentage"] == 91.5


def test_summary_error_is_propagated_to_reservation_record(monkeypatch):
    summary_failure = CollectorOutput.failed(
        "(AuthorizationFailed) caller lacks Reservations Reader on the order"
    )
    monkeypatch.setattr(
        reservations,
        "safe_run_json",
        _stub_run_json(
            [_orders_response(), _reservations_response(), summary_failure]
        ),
    )

    out = reservations.collect("sub-1")
    (rsv,) = out.data[0]["reservations"]
    assert "avgUtilizationPercentage" not in rsv
    assert "AuthorizationFailed" in rsv["_utilisation_error"]
