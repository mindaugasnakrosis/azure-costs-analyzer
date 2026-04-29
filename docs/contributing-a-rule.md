# Contributing a cost rule

A *rule* is a small Python module that reads collector payloads from a snapshot and yields `Finding`s. The discipline below keeps the bar consistent: every claim is grounded in a published authority, every saving is a range with a stated assumption, every Info finding leaves a clear path to a verdict.

## The order

1. **Author or update the knowledge document first** under `packages/azure-cost-investigator/src/azure_cost_investigator/knowledge/`.
2. **Add a rule module** under `packages/azure-cost-investigator/src/azure_cost_investigator/rules/<rule_id>.py`.
3. **Register it** in `rules/__init__.py` (`RULE_MODULES = (..., "<rule_id>")`).
4. **Write tests** under `packages/azure-cost-investigator/tests/test_rules_<rule_id>.py` using the `snapshot_factory` + `cost_knowledge` fixtures from `conftest.py`.
5. **Run the suite**: `uv run pytest packages/azure-cost-investigator`.

If you find yourself wanting to skip step 1, stop. A rule without a citation is the cardinal anti-pattern.

## Step 1 — the knowledge document

Each `knowledge/*.md` file leads with this frontmatter:

```yaml
---
title: <short title>
source_url: <canonical Microsoft / FinOps Foundation URL>
source_retrieved: 2026-04-29     # absolute date, never relative
source_sha256: <hex>             # populated by scripts/refresh_knowledge.py
cited_by: [<rule_id_1>, <rule_id_2>]
---
```

The body is a verbatim quote of the rule, threshold, or definition the analyser depends on, with a few sentences of surrounding commentary that name the rule(s) consuming it. Paraphrase is fine in commentary; the cited threshold itself is copied exactly.

If WebFetch can't reach the canonical page, write the file with a `TODO: fetch` placeholder and surface it in the build summary so the gap is visible.

## Step 2 — the rule module

```python
# packages/azure-cost-investigator/src/azure_cost_investigator/rules/<rule_id>.py
"""<rule_id> — one-line description.

Authority: `knowledge/<file>.md`. <One paragraph explaining why this rule
fires, what severity / confidence it carries, and what data it needs.>
"""

from __future__ import annotations
from typing import Iterable

from azure_investigator_core.schema import Confidence, Finding, Severity
from .base import RuleContext, info_missing_data, savings_range

RULE_ID = "<rule_id>"
KNOWLEDGE_REFS = ["<file>.md"]


def evaluate(ctx: RuleContext) -> Iterable[Finding]:
    findings: list[Finding] = []
    for sub in ctx.subscriptions():
        data = ctx.data_for(sub.id, "<collector_name>")
        if data is None:
            findings.append(
                info_missing_data(
                    rule_id=RULE_ID,
                    title="<Human title>",
                    subscription=sub,
                    missing_collector="<collector_name>",
                )
            )
            continue
        for r in data:
            if not _flags(r):
                continue
            findings.append(Finding(
                rule_id=RULE_ID,
                title=f"<concrete>: {r.get('name')}",
                subscription_id=sub.id,
                subscription_name=sub.name,
                region=r.get("location"),
                resource_id=r.get("id"),
                resource_name=r.get("name"),
                severity=Severity.MEDIUM,
                confidence=Confidence.HIGH,
                estimated_savings=savings_range(
                    low=..., high=...,
                    assumption=(
                        "Assumes <the load-bearing assumption>. "
                        "Band uses retail rates for <SKU>; actual savings "
                        "depend on negotiated discounts and reservations."
                    ),
                ),
                knowledge_refs=KNOWLEDGE_REFS,
                evidence={...},  # rule-specific structured detail
                recommended_investigation=(
                    "<Question to answer before deciding — never an action>"
                ),
            ))
    return findings
```

Required pieces:

- **`RULE_ID`** matches the filename (snake_case).
- **`KNOWLEDGE_REFS`** lists every `knowledge/*.md` file the rule cites. The analyser refuses to run if any are missing from the corpus.
- **`evaluate(ctx)`** yields zero or more `Finding`s. Always handle the missing-collector case via `info_missing_data` — it downgrades the rule to Info rather than running blind.
- **`Finding.severity`** picks from the rubric in `SKILL.md` (Critical → Info). Avoid severity inflation; "everything Medium" means you've stopped thinking.
- **`Finding.confidence`** picks from the rubric: High = deterministic from inventory, Medium = depends on a metrics window, Low = depends on assumed future workload.
- **`SavingsRange.assumption`** is a non-empty string (the schema validator enforces it). Lift it into the report verbatim — it's the load-bearing caveat.
- **`recommended_investigation`** is a *question*, not an action. Never suggest a write `az` command.

## Step 3 — register

```python
# packages/azure-cost-investigator/src/azure_cost_investigator/rules/__init__.py
RULE_MODULES = (
    ...,
    "<rule_id>",
)
```

## Step 4 — tests

The shared `conftest.py` exposes two fixtures:

- `snapshot_factory(per_sub: dict)` — builds a real on-disk snapshot from a per-subscription dict of collector payloads. Pass `None` as the payload to simulate a collector failure.
- `cost_knowledge` — loads the cost-skill knowledge corpus from the installed package.

Minimum test surface for a new rule:

1. **Positive**: a fixture that should fire returns the expected finding(s) with the right severity / confidence / savings band.
2. **Negative**: similar resources that should *not* fire stay quiet.
3. **Missing-collector**: payload `None` produces a single Info finding, not silence and not a crash.
4. **Knowledge refs**: every entry in `KNOWLEDGE_REFS` exists in the corpus (`cost_knowledge.has(ref)`).

Real-snapshot calibration is welcome — the `test_real_snapshot_smoke.py` pattern is to skip the test if the snapshot folder isn't present.

## Step 5 — run

```bash
uv run pytest packages/azure-cost-investigator
```

If a test passes only because the fixture is too permissive, fix the fixture, not the rule.

## Anti-patterns refused at review time

- ❌ Rule with no `KNOWLEDGE_REFS`.
- ❌ Knowledge document that paraphrases the authority instead of quoting verbatim.
- ❌ `SavingsRange` constructed directly with an empty `assumption` (Pydantic rejects it; don't bypass).
- ❌ `recommended_investigation` framed as an action ("Delete the disk").
- ❌ Severity Medium on every finding the rule emits (re-read the rubric).
- ❌ Adding a collector dependency without updating the rule's missing-collector branch.
