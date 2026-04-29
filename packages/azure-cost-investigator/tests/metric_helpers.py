"""Test helpers — synthesise vm_metrics records with controllable CPU profiles."""

from __future__ import annotations


def metric_record(
    *,
    vm_id: str,
    vm_name: str,
    region: str = "uksouth",
    points: int = 336,
    avg_pct: float = 5.0,
    p95_pct: float | None = None,
    max_pct: float | None = None,
) -> dict:
    """Produce a vm_metrics record with `points` hourly samples whose average
    matches `avg_pct`, with a small spread that includes a `p95_pct` and
    `max_pct` when provided."""
    p95_pct = p95_pct if p95_pct is not None else avg_pct
    max_pct = max_pct if max_pct is not None else p95_pct

    # Realistic distribution: ~95% of points at avg_pct, top ~5% at p95_pct,
    # one outlier at max_pct. Lines up with the rule's nearest-rank P95.
    spike_count = max(1, int(points * 0.05)) if points >= 20 else max(0, points - 1)
    base_count = max(0, points - spike_count - (1 if points >= 1 else 0))
    base = [avg_pct] * base_count + [p95_pct] * spike_count
    if points >= 1:
        base.append(max_pct)
    data = [
        {"average": v, "timeStamp": f"2026-04-{1 + (i % 28):02d}T00:00:00Z"}
        for i, v in enumerate(base)
    ]
    return {
        "vm_id": vm_id,
        "vm_name": vm_name,
        "region": region,
        "window_start": "2026-04-15T00:00:00Z",
        "window_end": "2026-04-29T00:00:00Z",
        "metrics": {
            "value": [
                {
                    "name": {"value": "Percentage CPU"},
                    "timeseries": [{"data": data}],
                    "unit": "Percent",
                }
            ]
        },
        "error": None,
    }


def vm_record(
    *,
    vm_id: str,
    name: str,
    sku: str = "Standard_D4s_v5",
    region: str = "uksouth",
    power_state: str = "VM running",
    tags: dict | None = None,
) -> dict:
    return {
        "id": vm_id,
        "name": name,
        "location": region,
        "powerState": power_state,
        "hardwareProfile": {"vmSize": sku},
        "tags": tags or {},
    }
