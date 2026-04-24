from __future__ import annotations

from dataclasses import dataclass, field
import math
from pathlib import Path
import re

_TOKEN_RE = re.compile(r"[a-zA-Z0-9_]{2,}")


def _tokenize(text: str) -> list[str]:
    return [match.group(0).lower() for match in _TOKEN_RE.finditer(text)]


def _ensure_directory(path: Path) -> Path:
    candidate = Path(path)

    def fallback_directory() -> Path:
        base_roots = [candidate.parent, (Path.cwd() / ".runtime" / "knowledge-store").resolve()]
        for base_root in base_roots:
            suffix = 1
            while True:
                fallback = base_root / f"{candidate.name}-store{suffix if suffix > 1 else ''}"
                if fallback.exists() and fallback.is_file():
                    suffix += 1
                    continue
                try:
                    fallback.mkdir(parents=True, exist_ok=True)
                except OSError:
                    break
                return fallback
        raise OSError(f"Unable to allocate a knowledge directory for {candidate}")

    lineage = [candidate, *candidate.parents]
    if any(item.exists() and item.is_file() for item in lineage):
        return fallback_directory()

    try:
        candidate.mkdir(parents=True, exist_ok=True)
    except FileExistsError:
        return fallback_directory()
    return candidate


@dataclass(frozen=True, slots=True)
class KnowledgeChunk:
    id: str
    source: str
    title: str
    content: str
    token_counts: dict[str, int]


@dataclass(frozen=True, slots=True)
class SearchHit:
    id: str
    source: str
    title: str
    snippet: str
    score: float


@dataclass(slots=True)
class KnowledgeIndex:
    root: Path
    chunks: list[KnowledgeChunk] = field(default_factory=list)
    document_frequencies: dict[str, int] = field(default_factory=dict)

    def __post_init__(self) -> None:
        self.root = _ensure_directory(self.root)

    def ensure_demo_content(self) -> None:
        if any(self.root.iterdir()):
            return
        (self.root / "welcome.md").write_text(
            "# ForgeChat\n\n"
            "ForgeChat is a local-first AI shell that is designed to sit in front of your own model APIs.\n"
            "Add product docs, API notes, and operating procedures to this knowledge folder so retrieval can ground answers.\n\n"
            "Tips:\n"
            "- Put specs and playbooks here.\n"
            "- Use fast mode for shorter responses and lower latency.\n"
            "- Point FORGE_API_URL at your own chat inference endpoint to replace the built-in mock provider.\n",
            encoding="utf-8",
        )

    def refresh(self) -> None:
        self.ensure_demo_content()
        chunks: list[KnowledgeChunk] = []
        doc_frequencies: dict[str, int] = {}
        chunk_index = 0
        for path in sorted(self.root.rglob("*")):
            if not path.is_file():
                continue
            if path.suffix.lower() not in {".md", ".txt", ".py", ".json", ".yaml", ".yml"}:
                continue
            text = path.read_text(encoding="utf-8", errors="ignore")
            for part_index, part in enumerate(self._split_text(text)):
                tokens = _tokenize(part)
                if not tokens:
                    continue
                token_counts: dict[str, int] = {}
                seen: set[str] = set()
                for token in tokens:
                    token_counts[token] = token_counts.get(token, 0) + 1
                    if token not in seen:
                        doc_frequencies[token] = doc_frequencies.get(token, 0) + 1
                        seen.add(token)
                chunks.append(
                    KnowledgeChunk(
                        id=f"chunk-{chunk_index}",
                        source=str(path.relative_to(self.root)),
                        title=f"{path.name} #{part_index + 1}",
                        content=part,
                        token_counts=token_counts,
                    )
                )
                chunk_index += 1
        self.chunks = chunks
        self.document_frequencies = doc_frequencies

    def add_document(self, name: str, content: str) -> None:
        safe_name = re.sub(r"[^a-zA-Z0-9_.-]", "-", name).strip("-") or "note.md"
        destination = self.root / safe_name
        destination.write_text(content, encoding="utf-8")
        self.refresh()

    def list_sources(self) -> list[str]:
        return sorted({chunk.source for chunk in self.chunks})

    def search(self, query: str, limit: int) -> list[SearchHit]:
        if not self.chunks:
            self.refresh()
        query_tokens = _tokenize(query)
        if not query_tokens:
            return []
        corpus_size = max(len(self.chunks), 1)
        scores: list[SearchHit] = []
        for chunk in self.chunks:
            score = 0.0
            for token in query_tokens:
                tf = chunk.token_counts.get(token, 0)
                if tf == 0:
                    continue
                df = self.document_frequencies.get(token, 0)
                idf = math.log((1 + corpus_size) / (1 + df)) + 1.0
                score += tf * idf
            if score <= 0.0:
                continue
            scores.append(
                SearchHit(
                    id=chunk.id,
                    source=chunk.source,
                    title=chunk.title,
                    snippet=self._highlight(chunk.content, query_tokens),
                    score=score,
                )
            )
        scores.sort(key=lambda hit: hit.score, reverse=True)
        return scores[:limit]

    def _split_text(self, text: str) -> list[str]:
        normalized = text.replace("\r\n", "\n").strip()
        if not normalized:
            return []
        blocks = [block.strip() for block in normalized.split("\n\n") if block.strip()]
        emitted: list[str] = []
        current = ""
        for block in blocks:
            candidate = f"{current}\n\n{block}".strip() if current else block
            if len(candidate) <= 900:
                current = candidate
                continue
            if current:
                emitted.append(current)
            if len(block) <= 900:
                current = block
            else:
                for start in range(0, len(block), 900):
                    emitted.append(block[start : start + 900])
                current = ""
        if current:
            emitted.append(current)
        return emitted

    def _highlight(self, content: str, query_tokens: list[str]) -> str:
        lines = [line.strip() for line in content.splitlines() if line.strip()]
        for line in lines:
            lower = line.lower()
            if any(token in lower for token in query_tokens):
                return line[:220]
        return content[:220].replace("\n", " ")
