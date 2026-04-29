from __future__ import annotations

import json
import time
from pathlib import Path

import httpx
from azure_investigator_core.pricing import PriceQuery, PricingClient

SAMPLE_BODY = {
    "BillingCurrency": "GBP",
    "CustomerEntityId": "Default",
    "CustomerEntityType": "Retail",
    "Items": [
        {
            "currencyCode": "GBP",
            "tierMinimumUnits": 0.0,
            "retailPrice": 0.0768,
            "unitPrice": 0.0768,
            "armRegionName": "uksouth",
            "armSkuName": "Standard_D2s_v5",
            "productName": "Virtual Machines Dsv5 Series",
            "skuName": "D2s v5",
            "serviceName": "Virtual Machines",
            "type": "Consumption",
            "unitOfMeasure": "1 Hour",
        }
    ],
    "NextPageLink": None,
    "Count": 1,
}


class _MockTransport(httpx.MockTransport):
    def __init__(self, recorded_body: dict, calls_holder: list):
        def handler(request):
            calls_holder.append(request)
            return httpx.Response(200, json=recorded_body)

        super().__init__(handler)


def _client(cache_root: Path, *, ttl_days: int = 7, calls=None) -> PricingClient:
    transport = _MockTransport(SAMPLE_BODY, calls if calls is not None else [])
    http = httpx.Client(transport=transport)
    return PricingClient(cache_root=cache_root, ttl_days=ttl_days, http=http)


def test_first_call_hits_network_second_uses_cache(tmp_path):
    calls: list[httpx.Request] = []
    client = _client(tmp_path, calls=calls)

    body1 = client.fetch("serviceName eq 'Virtual Machines'")
    body2 = client.fetch("serviceName eq 'Virtual Machines'")

    assert body1["Items"] == SAMPLE_BODY["Items"]
    assert body2["Items"] == SAMPLE_BODY["Items"]
    assert len(calls) == 1, "second call should be served from cache"


def test_cache_keyed_by_filter_and_currency(tmp_path):
    calls: list[httpx.Request] = []
    client = _client(tmp_path, calls=calls)
    client.fetch("serviceName eq 'X'")
    client.fetch("serviceName eq 'Y'")
    assert len(calls) == 2


def test_cache_expires(tmp_path):
    calls: list[httpx.Request] = []
    client = _client(tmp_path, ttl_days=0, calls=calls)
    client.fetch("serviceName eq 'X'")
    # bump cache file timestamp 1 day into the past so TTL=0 logic re-fetches
    (cache_file,) = tmp_path.glob("*.json")
    payload = json.loads(cache_file.read_text())
    payload["_cached_at"] = time.time() - 3600
    cache_file.write_text(json.dumps(payload))
    client.fetch("serviceName eq 'X'")
    assert len(calls) == 2


def test_currency_default_is_gbp(tmp_path):
    calls: list[httpx.Request] = []
    client = _client(tmp_path, calls=calls)
    client.fetch("serviceName eq 'X'")
    request = calls[0]
    assert "currencyCode=GBP" in str(request.url)


def test_items_unwraps(tmp_path):
    client = _client(tmp_path)
    items = client.items("serviceName eq 'Virtual Machines'")
    assert items[0]["armSkuName"] == "Standard_D2s_v5"


def test_price_query_cache_key_stable():
    a = PriceQuery(filter="x", currency="GBP")
    b = PriceQuery(filter="x", currency="GBP")
    c = PriceQuery(filter="x", currency="USD")
    assert a.cache_key == b.cache_key
    assert a.cache_key != c.cache_key
