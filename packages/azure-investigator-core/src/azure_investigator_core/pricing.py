"""Microsoft Retail Prices API client with on-disk JSON cache.

API: https://prices.azure.com/api/retail/prices  (anonymous, GBP supported via
`currencyCode=GBP`). Cache key is the canonicalised filter string + currency.
TTL is read from Config (default 7 days).

Rate-limit posture: the API is throttled but generous; this client is meant for
sporadic lookups inside rules, not for bulk dumps. Callers should batch by SKU.
"""

from __future__ import annotations

import hashlib
import json
import time
from collections.abc import Mapping
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import httpx

DEFAULT_BASE_URL = "https://prices.azure.com/api/retail/prices"


@dataclass(frozen=True)
class PriceQuery:
    filter: str
    currency: str = "GBP"

    @property
    def cache_key(self) -> str:
        norm = f"{self.currency}|{self.filter.strip()}"
        return hashlib.sha256(norm.encode("utf-8")).hexdigest()[:24]


class PricingClient:
    def __init__(
        self,
        cache_root: Path,
        ttl_days: int = 7,
        currency: str = "GBP",
        base_url: str = DEFAULT_BASE_URL,
        http: httpx.Client | None = None,
    ):
        self._cache_root = cache_root
        self._ttl_seconds = ttl_days * 86400
        self._currency = currency
        self._base_url = base_url
        self._http = http or httpx.Client(timeout=30.0)

    def _cache_path(self, query: PriceQuery) -> Path:
        return self._cache_root / f"{query.cache_key}.json"

    def _read_cache(self, query: PriceQuery) -> dict | None:
        path = self._cache_path(query)
        if not path.exists():
            return None
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            return None
        ts = payload.get("_cached_at")
        if ts is None:
            return None
        if time.time() - float(ts) > self._ttl_seconds:
            return None
        return payload

    def _write_cache(self, query: PriceQuery, body: dict) -> None:
        self._cache_root.mkdir(parents=True, exist_ok=True)
        body = dict(body)
        body["_cached_at"] = time.time()
        body["_cached_at_iso"] = datetime.now(UTC).isoformat()
        body["_query_filter"] = query.filter
        body["_currency"] = query.currency
        self._cache_path(query).write_text(json.dumps(body, default=str), encoding="utf-8")

    def fetch(self, filter_expr: str, *, currency: str | None = None) -> dict:
        """Fetch a single page of price items matching the OData filter.

        Returns the raw API response as a dict (with `Items`, `Count`, `NextPageLink`).
        Cached on disk for the configured TTL.
        """
        query = PriceQuery(filter=filter_expr, currency=currency or self._currency)
        cached = self._read_cache(query)
        if cached is not None:
            return cached

        params: Mapping[str, str] = {
            "$filter": query.filter,
            "currencyCode": query.currency,
        }
        resp = self._http.get(self._base_url, params=params)
        resp.raise_for_status()
        body: dict[str, Any] = resp.json()
        self._write_cache(query, body)
        return body

    def items(self, filter_expr: str, *, currency: str | None = None) -> list[dict]:
        body = self.fetch(filter_expr, currency=currency)
        return list(body.get("Items", []))

    def close(self) -> None:
        self._http.close()
