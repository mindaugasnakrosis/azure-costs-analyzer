---
title: FinOps Foundation framework — Principles and Phases
source_url: https://www.finops.org/framework/
source_retrieved: 2026-04-29
source_sha256: 44e68ab5855ec4ba98e3c72a04738005264121dbfb7ef44f4f64d5a440e2491e
cited_by:
  - underused_reservations
  - dev_skus_in_prod
  - untagged_costly_resources
---

The FinOps Foundation framework is the canonical model for cloud cost discipline. The cost analyser organises its narrative reporting around the three FinOps phases (Inform → Optimize → Operate) and grounds severity prioritisation in the six FinOps Principles.

## The Six FinOps Principles (verbatim)

The FinOps Foundation publishes six principles. As of the retrieval date these are:

1. Teams need to collaborate
2. Business value drives technology decisions
3. Everyone takes ownership for their technology usage
4. FinOps data should be accessible, timely, and accurate
5. FinOps should be enabled centrally
6. Take advantage of the variable cost model of the cloud

## The Three FinOps Phases

The FinOps journey consists of **Inform, Optimize and Operate** — quoted from the framework landing page. The framework page itself links out to a dedicated "Phases" article for the verbatim phase definitions and capabilities; that page was not captured in the same fetch as this file.

> TODO: refetch the per-phase definitions from <https://www.finops.org/framework/phases/> and inline them here. Until then, phase names are quoted; activities are cited from secondary FinOps Foundation publications below.

## Phase shape used by the analyser (commentary, not verbatim)

The cost analyser maps its rule outputs onto the three phases as follows. This mapping is **not** quoted from FinOps Foundation; it is the analyser's authoring convention, and is documented here so reviewers can challenge it.

| Phase | Analyser output |
| --- | --- |
| **Inform** | The "Total monthly savings range" + "Findings by severity" sections of the report; tagging-coverage gaps. |
| **Optimize** | The High/Critical findings (orphans, dev-SKUs-in-prod, oversized VMs). |
| **Operate** | The "Strategic recommendations" tail (reservation lifecycle, tagging policy, redundancy posture). |

---

**How rules use this:**

- The analyser's report.md groups findings into Inform/Optimize/Operate sections; the principles are cited in the "Why these matter" framing, not in individual finding bodies.
- `underused_reservations` cites Principle 6 ("variable cost model") as the strategic frame — a long-running unused reservation is a violation of the principle, not just a number.
