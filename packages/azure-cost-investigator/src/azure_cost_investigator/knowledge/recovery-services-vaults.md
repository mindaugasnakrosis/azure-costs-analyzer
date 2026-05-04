# Recovery Services Vault — backup retention & redundancy cost

## Authority

- [Azure Backup pricing (Microsoft)](https://azure.microsoft.com/en-us/pricing/details/backup/)
- [Azure Backup storage redundancy options](https://learn.microsoft.com/azure/backup/backup-create-rs-vault#set-storage-redundancy)
- [Long-term retention overview](https://learn.microsoft.com/azure/backup/backup-azure-vms-introduction#cloud-backup)
- [Azure Backup soft delete](https://learn.microsoft.com/azure/backup/backup-azure-security-feature-cloud)
- [Azure Backup pricing FAQ](https://azure.microsoft.com/en-us/pricing/details/backup/#faq)

## What costs money

A Recovery Services Vault bills on three independent axes:

1. **Protected-instance fee** — flat monthly fee per instance based on
   front-end size (≤50 GB ≈ £3.50/mo, ≤500 GB ≈ £7.00/mo, then
   +£7.00 per 500 GB). Charged regardless of how much actually changes.
2. **Backup storage** — incremental snapshot storage for the configured
   retention. Default is GeoRedundant (GRS) at ≈ **£0.038/GB-month**.
   Locally-redundant (LRS) is ≈ **£0.019/GB-month** — half the cost.
   Zone-redundant (ZRS) sits between at ≈ £0.024/GB-month.
3. **Long-term retention (LTR)** — monthly and yearly recovery points
   accumulate over time. Azure's portal default policy ("EnhancedPolicy")
   keeps **60 monthly** + **10 yearly** points, plus the daily/weekly
   schedule. For a 100 GB VM with ~10% monthly churn that is several ×
   the source size in storage by month 24.

## Detection signal

The `az backup vault list` payload exposes:

- `properties.storageType` — `LocallyRedundant` / `ZoneRedundant` /
  `GeoRedundant` (default).
- `properties.crossRegionRestore` — when GRS is enabled, this further
  doubles read pricing.
- `properties.softDeleteFeatureState` — `Enabled` (default 14-day soft
  delete) extends storage charges past the deletion event.

The `az backup policy list --vault-name X --resource-group Y` payload
exposes the retention schedule per policy:

- `properties.retentionPolicy.dailySchedule.retentionDuration.count` —
  daily recovery-point retention (typical 7–30 days).
- `properties.retentionPolicy.weeklySchedule.retentionDuration.count` —
  weekly retention in weeks (typical 4–12).
- `properties.retentionPolicy.monthlySchedule.retentionDuration.count` —
  monthly retention in months. Default policy keeps **60**.
- `properties.retentionPolicy.yearlySchedule.retentionDuration.count` —
  yearly retention in years. Default policy keeps **10**.

## When this tool flags a vault

A finding is emitted when **any** of:

1. `storageType == GeoRedundant` and the subscription is non-production
   (test/dev/uat/sandbox name match) — GRS pays for cross-region
   replication that test data does not need. Switching to LRS halves
   the storage line. **Severity**: Medium.
2. Any policy on the vault retains **monthly > 12** OR **yearly > 5**
   points. Most audit/compliance contracts (SOC 2, ISO 27001, HIPAA)
   require ≤ 7 years total; portal defaults far exceed typical contract
   minima. **Severity**: Medium.
3. `softDeleteFeatureState == Enabled` AND retention is already large —
   this combination has the highest blast-radius for storage cost
   surprises. **Severity**: Info (governance flag, not a £ saving).

## Savings band

Without per-vault used-storage in GB we cannot quote a precise £ figure.
The rule emits a band only when the consumption snapshot includes a
`Backup` MeterCategory line for the vault's resource ID; in that case we
apply:

- **GRS → LRS** flag: 30-day vault spend × **0.30** low to **0.50** high
  (the published GRS/LRS price ratio is ~2.0; we hold a margin for the
  protected-instance line that does not move).
- **Retention bloat** flag: 30-day vault spend × **0.20** low to **0.40**
  high. The factor reflects that yearly points dominate storage past
  month 24 and trimming the tail releases the bulk of the storage charge
  without affecting RPO/RTO for recent recovery.

If consumption data is missing, the finding still surfaces (governance
value) but with no band.

## Confidence

**Medium**. The rule sees the policy and the redundancy choice, but does
not know the customer's audit-compliance contract, RTO target, or the
true churn rate of each protected workload. The recommendation always
asks the user to confirm the compliance posture before reducing
retention or moving redundancy tier.
