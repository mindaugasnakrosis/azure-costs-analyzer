---
title: Standard SKU public IP billing and orphan detection
source_url: https://learn.microsoft.com/en-us/azure/virtual-network/ip-services/public-ip-addresses
source_retrieved: 2026-04-29
source_sha256: c412956be6655c79edc150d0b5f00c64caa8927470f84066a7d5ece9a5add9b7
cited_by:
  - unattached_public_ips
---

Standard SKU public IPs are statically allocated and bill regardless of attachment to a resource. Basic SKU public IPs were retired on 30 September 2025; any remaining Basic SKU IP is itself a finding.

## SKU retirement (verbatim, Microsoft Learn)

> On September 30, 2025, Basic SKU public IPs were retired. […] If you are currently using Basic SKU public IPs, make sure to upgrade to Standard SKU as soon as possible.

## Allocation method differences (verbatim)

> Public IP addresses can created with a SKU of **Standard (v1 or v2)** or **Basic**. The SKU determines their functionality including allocation method, feature support, and resources they can be associated with.
>
> | Public IP address | Standard (v1 or v2) | Basic |
> | --- | --- | --- |
> | Allocation method | Static | For IPv4: Dynamic or Static; For IPv6: Dynamic. |

## Pricing (verbatim)

> Public IPv4 addresses have a nominal charge; Public IPv6 addresses have no charge.

## Orphan signal

A public IP is orphan when its `ipConfiguration` is null — i.e. it is not associated with a network interface, load balancer front-end, gateway, or other supported resource type. Standard SKU IPv4 addresses in this state continue to bill for the duration of their existence. Microsoft's [public IP pricing page](https://azure.microsoft.com/pricing/details/ip-addresses) reports the unit charge per region.

---

**How the rule uses this:**

- `unattached_public_ips` flags any `Microsoft.Network/publicIPAddresses` resource where `ipConfiguration == null` AND `sku.name in {Standard, StandardV2}` AND `publicIPAddressVersion == IPv4`.
- Confidence: **High** — deterministic from inventory.
- A second tier of finding (severity: High) flags any remaining Basic SKU public IPv4 addresses given the post-retirement billing posture; Microsoft's own retirement guidance is cited verbatim in `recommended_investigation`.
