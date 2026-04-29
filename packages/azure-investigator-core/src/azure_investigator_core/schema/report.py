from __future__ import annotations

from datetime import datetime
from decimal import Decimal

from pydantic import BaseModel, ConfigDict, Field

from .finding import Finding, Severity


class Report(BaseModel):
    model_config = ConfigDict(extra="forbid")

    snapshot_id: str
    generated_at: datetime
    currency: str = "GBP"
    findings: list[Finding] = Field(default_factory=list)

    def by_severity(self, severity: Severity) -> list[Finding]:
        return [f for f in self.findings if f.severity == severity]

    def total_savings_range_gbp_per_month(self) -> tuple[Decimal, Decimal]:
        low = Decimal("0")
        high = Decimal("0")
        for f in self.findings:
            if f.estimated_savings is None:
                continue
            low += f.estimated_savings.low_gbp_per_month
            high += f.estimated_savings.high_gbp_per_month
        return low, high
