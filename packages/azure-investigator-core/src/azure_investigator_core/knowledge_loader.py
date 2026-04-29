"""Knowledge corpus loader.

A *knowledge corpus* is a folder of `.md` files shipped inside a skill's wheel,
each with YAML frontmatter naming the canonical source URL, retrieval date, and
content hash. Rules cite filenames; this loader exposes the corpus to rule code
and to the `knowledge` CLI verb.

Hard rule: `analyse` refuses to run a rule whose declared `knowledge_refs` are
not present in the corpus. That contract is enforced via `corpus.require()`.
"""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass, field
from importlib import resources
from importlib.resources.abc import Traversable
from pathlib import Path
from typing import Any

import yaml


@dataclass(frozen=True)
class KnowledgeDoc:
    filename: str
    frontmatter: dict[str, Any]
    body: str

    @property
    def title(self) -> str:
        return self.frontmatter.get("title", self.filename)

    @property
    def source_url(self) -> str | None:
        return self.frontmatter.get("source_url")

    @property
    def source_retrieved(self) -> str | None:
        v = self.frontmatter.get("source_retrieved")
        if v is None:
            return None
        # YAML 1.1 silently parses ISO dates into date objects; we always
        # surface them as ISO strings to keep the manifest output stable.
        return v.isoformat() if hasattr(v, "isoformat") else str(v)

    @property
    def source_sha256(self) -> str | None:
        return self.frontmatter.get("source_sha256")

    @property
    def cited_by(self) -> list[str]:
        return list(self.frontmatter.get("cited_by") or [])


@dataclass
class KnowledgeCorpus:
    package: str
    docs: dict[str, KnowledgeDoc] = field(default_factory=dict)

    @classmethod
    def load(cls, package: str, subpackage: str = "knowledge") -> KnowledgeCorpus:
        """Load every .md file under <package>/<subpackage>/.

        Returns an empty corpus if the package, subpackage, or directory is
        missing — used by the security-skill stub which has no corpus in v1.
        """
        corpus = cls(package=f"{package}.{subpackage}")
        try:
            root: Traversable = resources.files(package).joinpath(subpackage)
            if not root.is_dir():
                return corpus
            entries = list(root.iterdir())
        except (ModuleNotFoundError, FileNotFoundError, NotADirectoryError, OSError):
            return corpus
        for entry in entries:
            name = entry.name
            if not name.endswith(".md"):
                continue
            text = entry.read_text(encoding="utf-8")
            doc = parse_doc(name, text)
            corpus.docs[name] = doc
        return corpus

    @classmethod
    def from_path(cls, root: Path) -> KnowledgeCorpus:
        corpus = cls(package=str(root))
        if not root.exists():
            return corpus
        for path in sorted(root.glob("*.md")):
            corpus.docs[path.name] = parse_doc(path.name, path.read_text(encoding="utf-8"))
        return corpus

    def has(self, filename: str) -> bool:
        return filename in self.docs

    def get(self, filename: str) -> KnowledgeDoc:
        if filename not in self.docs:
            raise KeyError(
                f"knowledge document {filename!r} not present in corpus {self.package!r}."
            )
        return self.docs[filename]

    def require(self, refs: Iterable[str]) -> None:
        missing = [r for r in refs if r not in self.docs]
        if missing:
            raise FileNotFoundError(
                "Knowledge corpus is missing required documents: "
                f"{missing}. Each cited rule must ship its knowledge file."
            )

    def manifest(self) -> list[dict[str, Any]]:
        out: list[dict[str, Any]] = []
        for name in sorted(self.docs):
            doc = self.docs[name]
            out.append(
                {
                    "filename": name,
                    "title": doc.title,
                    "source_url": doc.source_url,
                    "source_retrieved": doc.source_retrieved,
                    "source_sha256": doc.source_sha256,
                    "cited_by": doc.cited_by,
                }
            )
        return out


def parse_doc(filename: str, text: str) -> KnowledgeDoc:
    fm, body = _split_frontmatter(text)
    return KnowledgeDoc(filename=filename, frontmatter=fm, body=body)


def _split_frontmatter(text: str) -> tuple[dict[str, Any], str]:
    if not text.startswith("---"):
        return {}, text
    parts = text.split("---", 2)
    if len(parts) < 3:
        return {}, text
    raw_fm = parts[1]
    body = parts[2].lstrip("\n")
    try:
        fm = yaml.safe_load(raw_fm) or {}
    except yaml.YAMLError:
        fm = {}
    if not isinstance(fm, dict):
        fm = {}
    return fm, body
