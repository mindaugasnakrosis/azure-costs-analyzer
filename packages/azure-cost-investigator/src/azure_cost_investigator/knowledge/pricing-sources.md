---
title: Microsoft Azure Retail Prices REST API
source_url: https://learn.microsoft.com/en-us/rest/api/cost-management/retail-prices/azure-retail-prices
source_retrieved: 2026-04-29
source_sha256: 2aea759ab576406a1ad27427d7588d59a838497e3709c383e8964195bfe1588f
cited_by:
  - oversized_vms
  - idle_vms
  - underused_reservations
  - legacy_storage_redundancy
---

The Retail Prices API is the canonical anonymous price source for Azure SKUs. The cost analyser's `pricing.PricingClient` is a thin wrapper over this endpoint with on-disk caching. GBP support is confirmed via the `currencyCode` parameter.

## Endpoint (verbatim)

> ## API endpoint
>
> `https://prices.azure.com/api/retail/prices`

## Currency support (verbatim)

> Important: The currency that Microsoft uses to price all Azure services is USD. Prices shown in USD currency are Microsoft retail prices. Other non-USD prices returned by the API are for your reference to help you estimate budget expenses.

> You can append the currency code to the API endpoint, as shown in the API sample call. For a complete list of supported currencies, see [Supported currencies].
>
> Example calls filtered for compute with currency in euro:
>
> ```http
> https://prices.azure.com/api/retail/prices?currencyCode='EUR'&$filter=serviceFamily eq 'Compute'
> ```

> Here's a sample response with a non-USD currency.
>
> ```json
> {
>   "currencyCode": "EUR",
>   "tierMinimumUnits": 0,
>   "retailPrice": 0.6176,
>   …
> }
> ```

GBP is included in Microsoft's [supported currencies list](https://learn.microsoft.com/en-us/azure/cost-management-billing/microsoft-customer-agreement/microsoft-customer-agreement-faq#how-is-azure-priced-under-the-microsoft-customer-agreement) for the Microsoft Customer Agreement. Non-USD prices are reference values for budgeting, not the prices Microsoft will bill against — the bill is always in the agreement currency.

## Filter syntax (verbatim)

> Filters are supported for the following fields:
>
> - `armRegionName`
> - `Location`
> - `meterId`
> - `meterName`
> - `productid`
> - `skuId`
> - `productName`
> - `skuName`
> - `serviceName`
> - `serviceId`
> - `serviceFamily`
> - `priceType`
> - `armSkuName`

> ### Filter value is case sensitive
>
> In previous API versions, the filter value wasn't case sensitive. However, in the `2023-01-01-preview` version and later, the value is case sensitive.

## Pagination (verbatim)

> The API response provides pagination. For each API request, a maximum of 1,000 records are returned. At the end of the API response, it has the link to next page.
>
> ```json
> "NextPageLink": https://prices.azure.com:443/api/retail/prices?$filter=serviceName%20eq%20%27Virtual%20Machines%27&$skip=1000
> ```

## Sample response (verbatim, Consumption record)

> ```json
> {
>   "currencyCode": "USD",
>   "tierMinimumUnits": 0.0,
>   "retailPrice": 0.176346,
>   "unitPrice": 0.176346,
>   "armRegionName": "westeurope",
>   "armSkuName": "Standard_F16s",
>   "serviceName": "Virtual Machines",
>   "unitOfMeasure": "1 Hour",
>   "type": "DevTestConsumption",
>   …
> }
> ```

---

**How the analyser uses this:**

- All price lookups go through `azure_investigator_core.pricing.PricingClient`. Currency defaults to GBP per `Config.currency`.
- Pricing is cached on disk with a 7-day TTL (configurable). The cache is keyed on the OData filter + currency and stamped with `_cached_at_iso` so reports are reproducible long after the snapshot.
- Microsoft's "non-USD prices are reference values" caveat is reflected in the analyser's `recommended_investigation` text on every savings finding: numbers are GBP-converted reference rates, not authoritative invoiced amounts.
