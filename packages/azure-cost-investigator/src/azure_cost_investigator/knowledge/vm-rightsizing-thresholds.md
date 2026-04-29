---
title: Azure Advisor — VM / VMSS shutdown and resize recommendation logic
source_url: https://learn.microsoft.com/en-us/azure/advisor/advisor-cost-recommendations
source_retrieved: 2026-04-29
source_sha256: f2400bc5000ab27e000273c6002a5fb4ea1756bb82bdc7c599a89746be7ae1bd
cited_by:
  - idle_vms
  - oversized_vms
---

The thresholds below are Microsoft's published criteria for the Advisor "Shut down" and "Resize" cost recommendations on virtual machines and virtual machine scale sets. They are quoted verbatim from the Advisor cost-recommendations how-to. Rule code calibrates against these so findings can be defended without invention.

## Shutdown recommendation criteria

> Advisor identifies resources that weren't used at all over the last seven days and makes a recommendation to shut them down.
>
> - Recommendation criteria include CPU and Outbound Network utilization metrics. Memory isn't considered since we found that CPU and Outbound Network utilization are sufficient.
> - The last seven days of utilization data are analyzed. You can change your lookback period in the configurations. The available lookback periods are 7, 14, 21, 30, 60, and 90 days. After you change the lookback period, it might take up to 48 hours for the recommendations to be updated.
> - Metrics are sampled every 30 seconds, aggregated to 1 min and then further aggregated to 30 mins (we take the max of average values while aggregating to 30 mins). On virtual machine scale sets, the metrics from individual virtual machines are aggregated using the average of the metrics across instances.
> - A shutdown recommendation is created if:
>   - P95 of the maximum value of CPU utilization summed across all cores is less than 3%
>   - P100 of average CPU in last 3 days (sum over all cores) <= 2%
>   - Outbound Network utilization is less than 2% over a seven-day period

## Resize SKU recommendation criteria

> Advisor recommends resizing virtual machines when it's possible to fit the current load on a more appropriate SKU, which is less expensive (based on retail rates).
>
> - Recommendation criteria include CPU, Memory, and Outbound Network utilization.
> - The last 7 days of utilization data are analyzed. You can change your lookback period in the configurations. The available lookback periods are 7, 14, 21, 30, 60, and 90 days.
> - An appropriate SKU (for virtual machines) or instance count (for virtual machine scale set resources) is determined based on the following criteria:
>   - Performance of the workloads on the new SKU isn't impacted.
>     - Target for user-facing workloads:
>       - P95 of CPU and Outbound Network utilization at 40% or lower on the recommended SKU
>       - P99 of Memory utilization at 60% or lower on the recommended SKU
>     - Target for non user-facing workloads:
>       - P95 of the CPU and Outbound Network utilization at 80% or lower on the new SKU
>       - P99 of Memory utilization at 80% or lower on the new SKU
>   - The new SKU, if applicable, has the same Accelerated Networking and Premium Storage capabilities
>   - The new SKU, if applicable, is supported in the current region of the Virtual Machine with the recommendation
>   - The new SKU, if applicable, is less expensive

## Burstable recommendation criteria

> A burstable SKU recommendation is made if:
>
> - The average CPU utilization is less than a burstable SKUs' baseline performance
>   - If the P95 of CPU is less than two times the burstable SKUs' baseline performance
>   - If the current SKU doesn't have accelerated networking enabled, since burstable SKUs don't support accelerated networking yet
>   - If we determine that the Burstable SKU credits are sufficient to support the average CPU utilization over 7 days.

## Limitations — must be reflected in our confidence rating

> The savings associated with the recommendations are based on retail rates and don't take into account any temporary or long-term discounts that might apply to your account. As a result, the listed savings might be higher than actually possible.
>
> The recommendations don't take into account the presence of Reserved Instances (RI) / Savings plan purchases. As a result, the listed savings might be higher than actually possible.

---

**How rules use this:**

- `idle_vms` flags a VM only when (P95 of CPU summed across cores) < 3% **and** (Outbound Network utilisation) < 2% over the configured 14-day window. We use 14 days, not Advisor's default 7, because PE-style audits look back longer.
- `oversized_vms` flags when the user-facing target cannot already be met (i.e. P95 CPU > 40% on current SKU but a smaller SKU would still keep P95 ≤ 40%). Confidence is Medium because workload classification (user-facing vs non) is heuristic.
- Both rules quote Microsoft's "limitations" caveat in `recommended_investigation`: savings figures are retail-rate ceilings, not floors, and don't net out reservations.
