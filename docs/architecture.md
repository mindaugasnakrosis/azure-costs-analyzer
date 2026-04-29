# Architecture — azure-investigator

This repo ships **one shared core package** plus **two Claude Code skills** that depend on it. The shape is deliberate; the rest of the document explains why.

## Layout

```
packages/
  azure-investigator-core/       # shared
  azure-cost-investigator/       # cost / FinOps skill (v1)
  azure-security-investigator/   # security skill (v2; stub today)
```

- **Skills never import each other.** Both depend only on `azure-investigator-core`.
- **Core owns** auth (`config`), the read-only `az` wrapper (`azcli`), the snapshot filesystem, the Retail Prices API client, the Pydantic schema (`Finding`, `SavingsRange`, `SnapshotManifest`, `Report`), and the knowledge corpus loader.
- **Each skill owns** its rules, knowledge corpus, persona prompt (`SKILL.md`), and verb-shaped CLI (`analyse`, `report`, …).

## Why two skills, one core

Persona is what makes a Claude Code skill credible. A single skill that's both *senior FinOps architect* and *senior security engineer* dilutes both — the prompts pull in opposite directions, and the user can't tell which voice they're getting. Splitting on persona, while sharing the read-only data plumbing, lets each skill stay sharp and lets the security skill ship later without reopening the cost skill's design.

The core package is the **architectural firewall**: it owns the Azure surface, enforces the read-only contract (`azcli.py` refuses 33 write verbs at the boundary), and exposes a stable schema. Skills never talk to Azure directly — they walk a snapshot folder produced by the core's `pull` verb.

## Data flow

```
  init  →  doctor  →  pull  →  analyse  →  narrate
   ↑        ↑         ↑          ↑           ↑
  core    core      core       skill       skill
```

1. `azure-investigator init` writes `~/.config/azure-investigator/config.yaml` after verifying `az login`.
2. `azure-investigator doctor` health-checks the environment + corpus.
3. `azure-investigator pull` snapshots every accessible subscription × every collector to `~/.local/share/azure-investigator/snapshots/<ISO-timestamp>/`. One bad collector for one subscription never aborts the run.
4. `azure-cost-investigator analyse <id|latest>` walks the rule registry, refuses to run a rule whose declared `knowledge_refs` are missing, writes `report.md` + `findings.yaml` next to the manifest.
5. The skill (Claude Code in the loop) narrates `report.md` to the user.

## Snapshots are reproducible artefacts

A snapshot is a complete on-disk record of a tenant at a moment in time. It includes per-subscription JSON for every collector plus a snapshot-time `pricing/` cache, so re-running `analyse` on the same snapshot months later yields the same report. This is what makes the artefact useful for PE-style audits — a finding can be defended against the data it was derived from, not against today's tenant state.

```
2026-04-29T14-41-29Z/
  manifest.yaml             # subs, collectors run, per-collector status
  subscriptions/<sub-id>/
    vms.json                # raw `az` output, one file per collector
    vm_metrics.json
    …
    collector_errors.json   # per-subscription failures (never fatal)
  pricing/                  # snapshot-time price cache
  report.md                 # written by `cost-investigator analyse`
  findings.yaml             # machine-readable findings list
```

## Read-only contract — enforced in three places

The "no Azure writes, ever" guarantee is load-bearing for the skill's positioning (you can run it against production without authorisation review). It is enforced at three levels:

1. **`azcli.py` allowlist.** Any `az` invocation whose tokens include a write verb (`update`, `delete`, `create`, `set`, `add`, `remove`, `assign`, `start`, `stop`, `restart`, `deallocate`, `tag update`, `lock`, `policy assignment`, …) raises `AzCliWriteRefused` before subprocess. 23 unit tests cover this.
2. **CLI verb naming.** No `apply`, `remediate`, `fix`, `delete` verbs anywhere. The naming itself is part of the contract.
3. **SKILL.md rule.** The cost skill's prompt explicitly forbids the model from suggesting write `az` commands; findings are framed as investigations to perform, not actions to take.

## Knowledge corpus — versioned, in-repo, citable

Every cost rule must cite at least one `knowledge/*.md` document. Each document leads with frontmatter (canonical source URL, retrieval date, content SHA-256, `cited_by` rule list) and contains *verbatim* quotes from the authority — paraphrase only in surrounding commentary. The analyser refuses to run a rule whose declared `knowledge_refs` are missing from the corpus.

This produces an auditable trail: a reviewer can ask "where does the £X figure come from?" and the answer is a Microsoft / FinOps Foundation URL plus the exact quoted threshold. A maintainer-only `scripts/refresh_knowledge.py` re-fetches the upstream pages and surfaces drift; humans review before commit.

## Why uv workspaces

Three editable installs from one root (`uv sync --all-packages`) give a clean dev loop: a change in `core/schema/finding.py` is immediately visible from a cost-skill rule test. The workspace declaration is in the root `pyproject.toml`; each package has its own `pyproject.toml` and ships its `knowledge/` folder via `force-include` so the corpus is present at runtime via `importlib.resources`.

## Severity vs confidence

The Pydantic schema treats severity and confidence as separate axes. Severity expresses how loud a finding should be (Critical → Info); confidence expresses how strong the inference is (High → Low). Two findings can sit at Medium severity but have very different confidence — and that distinction is what tells a reviewer where to push back. Savings are always ranges with a non-empty `assumption` string (enforced in the schema validator).
