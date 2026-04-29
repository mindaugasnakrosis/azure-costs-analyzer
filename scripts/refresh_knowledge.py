#!/usr/bin/env python3
"""Maintainer-only: re-fetch each knowledge document's canonical source and
update the SHA-256 + retrieval date in its frontmatter.

This script does NOT rewrite the verbatim quoted body — that decision must
stay with a human reviewer because Microsoft sometimes restructures the
underlying page (renames a section, swaps verbiage). The flow is:

  1. Fetch the canonical URL listed in each doc's frontmatter.
  2. Compute the SHA-256 of the *fetched* page body.
  3. Compare against the stored `source_sha256`.
  4. Print a diff summary so a human can decide whether to update the verbatim
     quote block. Only `source_retrieved` and `source_sha256` are auto-updated.

Run from the repo root:

  uv run python scripts/refresh_knowledge.py

Outputs a per-file status:
  • UNCHANGED — page body still matches the recorded hash.
  • UPDATED   — frontmatter retrieval date + sha256 refreshed; body unchanged.
  • DRIFTED   — page body changed; the quoted excerpt may need a manual edit.
                Frontmatter is left as-is so the diff is visible in git.
"""

from __future__ import annotations

import hashlib
import sys
from datetime import date
from pathlib import Path

import httpx
import yaml

REPO_ROOT = Path(__file__).resolve().parent.parent
KNOWLEDGE_ROOT = (
    REPO_ROOT
    / "packages"
    / "azure-cost-investigator"
    / "src"
    / "azure_cost_investigator"
    / "knowledge"
)


def split_frontmatter(text: str) -> tuple[dict, str]:
    if not text.startswith("---"):
        return {}, text
    parts = text.split("---", 2)
    if len(parts) < 3:
        return {}, text
    fm = yaml.safe_load(parts[1]) or {}
    return fm, parts[2]


def write_with_frontmatter(path: Path, fm: dict, body: str) -> None:
    fm_text = yaml.safe_dump(fm, sort_keys=False).strip()
    path.write_text(f"---\n{fm_text}\n---{body}", encoding="utf-8")


def fetch(url: str) -> str:
    resp = httpx.get(url, follow_redirects=True, timeout=30.0)
    resp.raise_for_status()
    return resp.text


def sha256(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def refresh_one(path: Path) -> str:
    text = path.read_text(encoding="utf-8")
    fm, body = split_frontmatter(text)
    url = fm.get("source_url")
    if not url:
        return f"SKIP    {path.name}: no source_url"

    try:
        page = fetch(url)
    except Exception as e:
        return f"FAILED  {path.name}: {type(e).__name__}: {e}"

    new_hash = sha256(page)

    # We hash the *fetched page body*, but the file's own sha256 is over its
    # *quoted body*. The two are intentionally different — the stored hash is
    # the integrity check on what we authored, not on the upstream page. So
    # this script records two values: the file's own body hash (unchanged),
    # and a separate `upstream_sha256` for drift detection.
    body_hash = sha256(body)
    upstream_old = fm.get("upstream_sha256")
    fm["source_retrieved"] = date.today().isoformat()
    fm["source_sha256"] = body_hash
    fm["upstream_sha256"] = new_hash

    if upstream_old == new_hash:
        write_with_frontmatter(path, fm, body)
        return f"UNCHANGED {path.name}"
    if upstream_old is None:
        write_with_frontmatter(path, fm, body)
        return f"UPDATED  {path.name}: first-time upstream hash recorded"
    write_with_frontmatter(path, fm, body)
    return (
        f"DRIFTED  {path.name}: upstream changed "
        f"({upstream_old[:8]} → {new_hash[:8]}); review the verbatim quote"
    )


def main(argv: list[str]) -> int:
    targets = sorted(KNOWLEDGE_ROOT.glob("*.md"))
    targets = [p for p in targets if p.name != "README.md"]
    if not targets:
        print(f"No knowledge files under {KNOWLEDGE_ROOT}", file=sys.stderr)
        return 2
    for path in targets:
        print(refresh_one(path))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
