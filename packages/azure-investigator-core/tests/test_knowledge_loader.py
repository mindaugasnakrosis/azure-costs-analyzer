from __future__ import annotations

import pytest
from azure_investigator_core.knowledge_loader import KnowledgeCorpus, parse_doc

SAMPLE = """---
title: VM right-sizing thresholds
source_url: https://learn.microsoft.com/example
source_retrieved: 2026-04-29
source_sha256: deadbeef
cited_by:
  - idle_vms
  - oversized_vms
---

The Advisor recommends right-sizing when average CPU < 5% over 14 days.
"""


def test_parse_doc_extracts_frontmatter_and_body():
    doc = parse_doc("vm-rightsizing-thresholds.md", SAMPLE)
    assert doc.title == "VM right-sizing thresholds"
    assert doc.source_url == "https://learn.microsoft.com/example"
    assert doc.source_retrieved == "2026-04-29"
    assert doc.source_sha256 == "deadbeef"
    assert doc.cited_by == ["idle_vms", "oversized_vms"]
    assert "average CPU" in doc.body


def test_no_frontmatter_returns_empty_dict():
    doc = parse_doc("plain.md", "hello world\n")
    assert doc.frontmatter == {}
    assert doc.body == "hello world\n"


def test_corpus_from_path(tmp_path):
    (tmp_path / "a.md").write_text(SAMPLE, encoding="utf-8")
    (tmp_path / "b.md").write_text("---\ntitle: B\n---\n\nbody\n", encoding="utf-8")
    corpus = KnowledgeCorpus.from_path(tmp_path)
    assert set(corpus.docs) == {"a.md", "b.md"}
    assert corpus.has("a.md")
    assert corpus.get("b.md").title == "B"


def test_corpus_require_raises_for_missing(tmp_path):
    (tmp_path / "a.md").write_text(SAMPLE, encoding="utf-8")
    corpus = KnowledgeCorpus.from_path(tmp_path)
    corpus.require(["a.md"])  # ok
    with pytest.raises(FileNotFoundError, match="missing required documents"):
        corpus.require(["a.md", "b.md"])


def test_manifest_lists_each_doc(tmp_path):
    (tmp_path / "a.md").write_text(SAMPLE, encoding="utf-8")
    corpus = KnowledgeCorpus.from_path(tmp_path)
    m = corpus.manifest()
    assert m[0]["filename"] == "a.md"
    assert m[0]["cited_by"] == ["idle_vms", "oversized_vms"]


def test_load_from_installed_cost_skill():
    """The cost skill ships an empty knowledge folder today; the loader still works."""
    corpus = KnowledgeCorpus.load("azure_cost_investigator")
    # Files exist in the source tree but are empty placeholders for now —
    # the loader still indexes them by name.
    assert isinstance(corpus.docs, dict)
