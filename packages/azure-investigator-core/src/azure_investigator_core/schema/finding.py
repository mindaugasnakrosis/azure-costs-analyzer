from __future__ import annotations

from decimal import Decimal
from enum import StrEnum
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, model_validator


class Severity(StrEnum):
    CRITICAL = "Critical"
    HIGH = "High"
    MEDIUM = "Medium"
    LOW = "Low"
    INFO = "Info"


class Confidence(StrEnum):
    HIGH = "High"
    MEDIUM = "Medium"
    LOW = "Low"


class SavingsRange(BaseModel):
    model_config = ConfigDict(extra="forbid")

    low_gbp_per_month: Decimal
    high_gbp_per_month: Decimal
    assumption: str

    @model_validator(mode="after")
    def _validate(self) -> SavingsRange:
        if not self.assumption or not self.assumption.strip():
            raise ValueError(
                "SavingsRange.assumption must be a non-empty string. "
                "Every savings estimate must state the workload assumption it depends on."
            )
        if self.low_gbp_per_month < 0 or self.high_gbp_per_month < 0:
            raise ValueError("SavingsRange amounts must be non-negative.")
        if self.low_gbp_per_month > self.high_gbp_per_month:
            raise ValueError(
                f"SavingsRange.low ({self.low_gbp_per_month}) must be <= "
                f"SavingsRange.high ({self.high_gbp_per_month})."
            )
        return self


class Finding(BaseModel):
    model_config = ConfigDict(extra="forbid", use_enum_values=False)

    rule_id: str
    title: str
    subscription_id: str
    subscription_name: str
    region: str | None = None
    resource_id: str | None = None
    resource_name: str | None = None
    severity: Severity
    confidence: Confidence
    current_monthly_cost_gbp: Decimal | None = None
    estimated_savings: SavingsRange | None = None
    knowledge_refs: list[str] = Field(default_factory=list)
    evidence: dict[str, Any] = Field(default_factory=dict)
    recommended_investigation: str

    @model_validator(mode="after")
    def _validate(self) -> Finding:
        if not self.rule_id.strip():
            raise ValueError("Finding.rule_id is required.")
        if not self.subscription_id.strip():
            raise ValueError("Finding.subscription_id is required.")
        if not self.recommended_investigation.strip():
            raise ValueError(
                "Finding.recommended_investigation is required: state the question to "
                "answer before deciding, not an action to take."
            )
        if self.severity != Severity.INFO and not self.knowledge_refs:
            raise ValueError(
                f"Finding {self.rule_id!r} (severity={self.severity.value}) must cite "
                "at least one knowledge_refs entry. Info-level findings are exempt "
                "(used for 'could not evaluate — missing data')."
            )
        return self
