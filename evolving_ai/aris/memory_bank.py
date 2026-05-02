from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
import hashlib
import json
from pathlib import Path
import re
from typing import Any, Iterable

from src.constants_runtime import ARIS_DOC_CHANNEL_ID, ARIS_HANDBOOK_ID, UL_ROOT_LAW_ID
from src.foundation_store import FoundationStore
from src.law_ledger import LawLedger


MEMORY_LAYERS = (
    "foundational",
    "operational",
    "learned_patterns",
    "rejected_patterns",
    "archive",
)

LIVE_MEMORY_LAYERS = (
    "foundational",
    "operational",
    "learned_patterns",
)

RETRIEVAL_LAYERS = (
    "foundational",
    "operational",
    "learned_patterns",
    "rejected_patterns",
)

AUTHORITY_LEVELS = {
    "foundational": 1000,
    "operational": 700,
    "learned_patterns": 500,
    "rejected_patterns": 350,
    "archive": 100,
}

IMMUTABLE_ENTRY_IDS = frozenset({ARIS_HANDBOOK_ID, ARIS_DOC_CHANNEL_ID, UL_ROOT_LAW_ID})

ROOT_TAGS = {
    ARIS_HANDBOOK_ID: ("aris", "handbook", "foundation", "immutable"),
    ARIS_DOC_CHANNEL_ID: ("aris", "doc-channel", "foundation", "immutable"),
    UL_ROOT_LAW_ID: ("ul", "law", "foundation", "immutable"),
}

_USER_MEMORY_PATTERNS: tuple[tuple[str, re.Pattern[str]], ...] = (
    ("name", re.compile(r"\bmy name is ([a-zA-Z][a-zA-Z0-9 _-]{1,40})", re.IGNORECASE)),
    ("preference", re.compile(r"\bi prefer ([^.!\n]{2,120})", re.IGNORECASE)),
    ("role", re.compile(r"\bi am (a|an)\s+([^.!\n]{2,120})", re.IGNORECASE)),
    ("project", re.compile(r"\bi(?:'m| am)? building ([^.!\n]{2,120})", re.IGNORECASE)),
)


def _utc_now() -> str:
    return datetime.now(UTC).isoformat()


def _normalize_text(value: str) -> str:
    return re.sub(r"\s+", " ", str(value or "").strip())


def _ensure_tags(tags: Iterable[str] | None) -> list[str]:
    normalized = {_normalize_text(tag).lower() for tag in (tags or []) if _normalize_text(tag)}
    return sorted(normalized)


def _entry_id(*, layer: str, entry_type: str, summary: str, content: str) -> str:
    digest = hashlib.sha256(
        "|".join(
            [
                layer.strip().lower(),
                entry_type.strip().lower(),
                _normalize_text(summary).lower(),
                _normalize_text(content).lower(),
            ]
        ).encode("utf-8")
    ).hexdigest()
    return f"{layer}-{digest[:16]}"


@dataclass(frozen=True, slots=True)
class GovernedMemoryEntry:
    id: str
    layer: str
    type: str
    authority_level: int
    source: str
    created_at: str
    updated_at: str
    status: str
    summary: str
    content: str
    tags: tuple[str, ...]

    @classmethod
    def from_payload(cls, payload: dict[str, Any], *, layer: str) -> "GovernedMemoryEntry":
        normalized_layer = str(layer or "").strip()
        if normalized_layer not in MEMORY_LAYERS:
            raise ValueError(f"Unknown memory layer: {layer}")
        entry_type = _normalize_text(str(payload.get("type", ""))) or "note"
        summary = _normalize_text(str(payload.get("summary", "")))
        content = _normalize_text(str(payload.get("content", "")))
        entry_id = _normalize_text(str(payload.get("id", ""))) or _entry_id(
            layer=normalized_layer,
            entry_type=entry_type,
            summary=summary,
            content=content,
        )
        authority_level = int(payload.get("authority_level", AUTHORITY_LEVELS[normalized_layer]))
        source = _normalize_text(str(payload.get("source", ""))) or "unknown"
        created_at = _normalize_text(str(payload.get("created_at", ""))) or _utc_now()
        updated_at = _normalize_text(str(payload.get("updated_at", ""))) or created_at
        status = _normalize_text(str(payload.get("status", ""))) or "active"
        tags = tuple(_ensure_tags(payload.get("tags")))
        return cls(
            id=entry_id,
            layer=normalized_layer,
            type=entry_type,
            authority_level=authority_level,
            source=source,
            created_at=created_at,
            updated_at=updated_at,
            status=status,
            summary=summary,
            content=content,
            tags=tags,
        )

    def payload(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "layer": self.layer,
            "type": self.type,
            "authority_level": self.authority_level,
            "source": self.source,
            "created_at": self.created_at,
            "updated_at": self.updated_at,
            "status": self.status,
            "summary": self.summary,
            "content": self.content,
            "tags": list(self.tags),
        }


class GovernedMemoryBank:
    """Authority-ordered ARIS memory with immutable foundational roots."""

    def __init__(self, root: Path, *, foundation_root: Path | None = None) -> None:
        self.root = root.resolve()
        self.root.mkdir(parents=True, exist_ok=True)
        self.foundation_root = (foundation_root or (self.root.parent / "foundation")).resolve()
        self.foundation_store = FoundationStore(self.foundation_root)
        self.law_ledger = LawLedger(self.foundation_root / "law_ledger.jsonl")
        self.layer_paths = {layer: self.root / f"{layer}.json" for layer in MEMORY_LAYERS}
        self._ensure_storage()

    def _ensure_storage(self) -> None:
        self._sync_foundational_projection()
        for layer in MEMORY_LAYERS:
            if layer == "foundational":
                continue
            path = self.layer_paths[layer]
            if not path.exists():
                path.write_text("[]\n", encoding="utf-8")

    def _sync_foundational_projection(self) -> None:
        entries: list[dict[str, Any]] = []
        now = _utc_now()
        for entry_id, item in sorted(self.foundation_store.entries().items()):
            content = _normalize_text(str(item.get("content", "")))
            entry_type = _normalize_text(str(item.get("class", ""))) or "FOUNDATIONAL_MEMORY"
            authority_level = 1100 if entry_id == ARIS_HANDBOOK_ID else 1050
            if entry_id == ARIS_DOC_CHANNEL_ID:
                authority_level = 1075
            entries.append(
                GovernedMemoryEntry(
                    id=entry_id,
                    layer="foundational",
                    type=entry_type,
                    authority_level=authority_level,
                    source="foundation_store",
                    created_at=now,
                    updated_at=now,
                    status="locked",
                    summary=(
                        "ARIS Handbook root memory."
                        if entry_id == ARIS_HANDBOOK_ID
                        else (
                            "ARIS Doc Channel root memory."
                            if entry_id == ARIS_DOC_CHANNEL_ID
                            else "UL root law memory."
                        )
                    ),
                    content=content,
                    tags=ROOT_TAGS.get(entry_id, ("foundation", "immutable")),
                ).payload()
            )
        self.layer_paths["foundational"].write_text(json.dumps(entries, indent=2), encoding="utf-8")

    def _read_layer(self, layer: str) -> list[GovernedMemoryEntry]:
        if layer not in MEMORY_LAYERS:
            raise ValueError(f"Unknown memory layer: {layer}")
        if layer == "foundational":
            self._sync_foundational_projection()
        path = self.layer_paths[layer]
        try:
            raw = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            backup = path.with_suffix(path.suffix + ".corrupt")
            try:
                if path.exists():
                    path.replace(backup)
            except OSError:
                pass
            if layer == "foundational":
                self._sync_foundational_projection()
                raw = json.loads(path.read_text(encoding="utf-8"))
            else:
                path.write_text("[]\n", encoding="utf-8")
                raw = []
        if not isinstance(raw, list):
            if layer == "foundational":
                self._sync_foundational_projection()
                raw = json.loads(path.read_text(encoding="utf-8"))
            else:
                backup = path.with_suffix(path.suffix + ".corrupt")
                try:
                    path.replace(backup)
                except OSError:
                    pass
                path.write_text("[]\n", encoding="utf-8")
                raw = []
        return [GovernedMemoryEntry.from_payload(dict(item), layer=layer) for item in raw if isinstance(item, dict)]

    def _write_layer(self, layer: str, entries: Iterable[GovernedMemoryEntry]) -> None:
        if layer == "foundational":
            raise PermissionError("Foundational memory is immutable and may not be overwritten casually.")
        payload = [entry.payload() for entry in entries]
        self.layer_paths[layer].write_text(json.dumps(payload, indent=2), encoding="utf-8")

    def _record_memory_event(self, kind: str, payload: dict[str, Any]) -> None:
        self.law_ledger.record(kind, payload, require_success=True)

    def schema_payload(self) -> dict[str, Any]:
        return {
            "fields": [
                "id",
                "type",
                "authority_level",
                "source",
                "created_at",
                "updated_at",
                "status",
                "summary",
                "content",
                "tags",
            ],
            "layers": list(MEMORY_LAYERS),
            "foundational_root_id": ARIS_HANDBOOK_ID,
        }

    def folder_structure_payload(self) -> dict[str, Any]:
        return {
            "root": str(self.root),
            "layers": {layer: str(path) for layer, path in self.layer_paths.items()},
            "foundation_store": str(self.foundation_root / "foundation_store.json"),
            "ledger": str(self.foundation_root / "law_ledger.jsonl"),
        }

    def retrieval_rules_payload(self) -> dict[str, Any]:
        return {
            "authority_order": list(MEMORY_LAYERS),
            "live_reasoning_layers": list(LIVE_MEMORY_LAYERS),
            "archive_excluded_by_default": True,
            "rejected_patterns_excluded_from_primary_context": True,
            "foundational_first": True,
        }

    def admission_rules_payload(self) -> dict[str, Any]:
        return {
            "foundational_requires_external_reseal": True,
            "operational_supports_runtime_state": True,
            "learned_patterns_require_admitted_usefulness": True,
            "rejected_patterns_preserve_failed_paths": True,
            "archive_is_non_live_history": True,
        }

    def status_payload(self) -> dict[str, Any]:
        counts = {layer: len(self._read_layer(layer)) for layer in MEMORY_LAYERS}
        return {
            "active": True,
            "root": str(self.root),
            "counts": counts,
            "authority_levels": dict(AUTHORITY_LEVELS),
            "schema": self.schema_payload(),
            "folder_structure": self.folder_structure_payload(),
            "retrieval_rules": self.retrieval_rules_payload(),
            "admission_rules": self.admission_rules_payload(),
        }

    def entries(
        self,
        *,
        layer: str | None = None,
        include_archive: bool = True,
        include_rejected: bool = True,
    ) -> list[GovernedMemoryEntry]:
        layers = [layer] if layer else list(MEMORY_LAYERS)
        items: list[GovernedMemoryEntry] = []
        for name in layers:
            if name == "archive" and not include_archive:
                continue
            if name == "rejected_patterns" and not include_rejected:
                continue
            items.extend(self._read_layer(name))
        return sorted(items, key=lambda entry: (-entry.authority_level, entry.updated_at, entry.id))

    def locked_entries(self) -> list[dict[str, Any]]:
        return [
            {
                "id": entry.id,
                "class": entry.type,
                "authority_level": entry.authority_level,
                "summary": entry.summary,
                "content": entry.content,
            }
            for entry in self._read_layer("foundational")
        ]

    def get(self, entry_id: str) -> GovernedMemoryEntry | None:
        needle = _normalize_text(entry_id)
        for entry in self.entries():
            if entry.id == needle:
                return entry
        return None

    def admit_entry(
        self,
        *,
        layer: str,
        entry_type: str,
        source: str,
        summary: str,
        content: str,
        tags: Iterable[str] | None = None,
        status: str = "active",
        entry_id: str = "",
        authority_level: int | None = None,
    ) -> GovernedMemoryEntry:
        normalized_layer = _normalize_text(layer)
        if normalized_layer not in MEMORY_LAYERS:
            raise ValueError(f"Unknown memory layer: {layer}")
        if normalized_layer == "foundational":
            raise PermissionError("Foundational memory is locked and requires external redesign/reseal.")
        now = _utc_now()
        entry = GovernedMemoryEntry(
            id=_normalize_text(entry_id)
            or _entry_id(
                layer=normalized_layer,
                entry_type=entry_type,
                summary=summary,
                content=content,
            ),
            layer=normalized_layer,
            type=_normalize_text(entry_type) or "note",
            authority_level=int(authority_level or AUTHORITY_LEVELS[normalized_layer]),
            source=_normalize_text(source) or "unknown",
            created_at=now,
            updated_at=now,
            status=_normalize_text(status) or "active",
            summary=_normalize_text(summary),
            content=_normalize_text(content),
            tags=tuple(_ensure_tags(tags)),
        )
        existing = {item.id: item for item in self._read_layer(normalized_layer)}
        previous = existing.get(entry.id)
        if previous is not None:
            entry = GovernedMemoryEntry(
                id=previous.id,
                layer=previous.layer,
                type=entry.type or previous.type,
                authority_level=entry.authority_level or previous.authority_level,
                source=entry.source or previous.source,
                created_at=previous.created_at,
                updated_at=now,
                status=entry.status or previous.status,
                summary=entry.summary or previous.summary,
                content=entry.content or previous.content,
                tags=tuple(sorted(set(previous.tags).union(entry.tags))),
            )
        existing[entry.id] = entry
        self._write_layer(normalized_layer, existing.values())
        self._record_memory_event(
            "governed_memory_admitted",
            {"layer": normalized_layer, "entry": entry.payload()},
        )
        return entry

    def update_entry(
        self,
        entry_id: str,
        *,
        summary: str | None = None,
        content: str | None = None,
        status: str | None = None,
        tags: Iterable[str] | None = None,
        source: str = "update",
    ) -> GovernedMemoryEntry:
        existing = self.get(entry_id)
        if existing is None:
            raise KeyError(entry_id)
        if existing.layer == "foundational" or existing.id in IMMUTABLE_ENTRY_IDS:
            raise PermissionError(f"{entry_id} is foundational and may not be overwritten.")
        updated = GovernedMemoryEntry(
            id=existing.id,
            layer=existing.layer,
            type=existing.type,
            authority_level=existing.authority_level,
            source=_normalize_text(source) or existing.source,
            created_at=existing.created_at,
            updated_at=_utc_now(),
            status=_normalize_text(status) or existing.status,
            summary=_normalize_text(summary) or existing.summary,
            content=_normalize_text(content) or existing.content,
            tags=tuple(sorted(set(existing.tags).union(_ensure_tags(tags)))),
        )
        items = {item.id: item for item in self._read_layer(existing.layer)}
        items[updated.id] = updated
        self._write_layer(existing.layer, items.values())
        self._record_memory_event(
            "governed_memory_updated",
            {"layer": existing.layer, "entry": updated.payload()},
        )
        return updated

    def archive_entry(self, entry_id: str, *, source: str, notes: str = "") -> GovernedMemoryEntry:
        existing = self.get(entry_id)
        if existing is None:
            raise KeyError(entry_id)
        archived = self.admit_entry(
            layer="archive",
            entry_type=existing.type,
            source=source,
            summary=existing.summary,
            content=existing.content if not notes else f"{existing.content}\n\nArchive notes: {notes}",
            tags=existing.tags,
            status="archived",
        )
        if existing.layer != "archive" and existing.layer != "foundational":
            self.update_entry(existing.id, status="archived", source=source)
        return archived

    def admit_learned_pattern(
        self,
        *,
        name: str,
        summary: str,
        content: str,
        source: str,
        tags: Iterable[str] | None = None,
    ) -> GovernedMemoryEntry:
        return self.admit_entry(
            layer="learned_patterns",
            entry_type=name,
            source=source,
            summary=summary,
            content=content,
            tags=tags,
            status="admitted",
        )

    def reject_pattern(
        self,
        *,
        name: str,
        summary: str,
        content: str,
        source: str,
        tags: Iterable[str] | None = None,
    ) -> GovernedMemoryEntry:
        return self.admit_entry(
            layer="rejected_patterns",
            entry_type=name,
            source=source,
            summary=summary,
            content=content,
            tags=tags,
            status="rejected",
        )

    def remember_from_user_text(self, text: str, *, source: str = "user") -> list[GovernedMemoryEntry]:
        additions: list[GovernedMemoryEntry] = []
        normalized_text = str(text or "")
        for category, pattern in _USER_MEMORY_PATTERNS:
            for match in pattern.finditer(normalized_text):
                value = _normalize_text(" ".join(group for group in match.groups() if group))
                if not value:
                    continue
                additions.append(
                    self.admit_entry(
                        layer="operational",
                        entry_type=category,
                        source=source,
                        summary=f"{category}: {value}",
                        content=value,
                        tags=("session", category),
                    )
                )
        return additions

    def _query_score(self, entry: GovernedMemoryEntry, query_terms: tuple[str, ...]) -> int:
        if not query_terms:
            return 1
        haystack = " ".join(
            [entry.type, entry.summary, entry.content, " ".join(entry.tags)]
        ).lower()
        return sum(1 for term in query_terms if term in haystack)

    def retrieve(
        self,
        *,
        query: str = "",
        limit: int = 10,
        include_archive: bool = False,
        include_rejected: bool = False,
    ) -> list[dict[str, Any]]:
        query_terms = tuple(
            term for term in re.findall(r"[a-z0-9_]{3,}", str(query or "").lower()) if term
        )
        layers = list(RETRIEVAL_LAYERS)
        if include_archive:
            layers.append("archive")
        if include_rejected and "rejected_patterns" not in layers:
            layers.append("rejected_patterns")
        candidates: list[tuple[int, GovernedMemoryEntry]] = []
        for layer in layers:
            for entry in self._read_layer(layer):
                if layer == "archive" and not include_archive:
                    continue
                if layer == "rejected_patterns" and not include_rejected:
                    continue
                if layer in LIVE_MEMORY_LAYERS and entry.status not in {"active", "admitted", "locked"}:
                    continue
                score = self._query_score(entry, query_terms)
                if query_terms and score == 0:
                    continue
                candidates.append((score, entry))
        ordered = sorted(
            candidates,
            key=lambda item: (-item[1].authority_level, -item[0], item[1].updated_at, item[1].id),
        )
        return [entry.payload() for _, entry in ordered[: max(1, limit)]]

    def summary(self, *, query: str = "", limit: int = 8) -> str:
        context = self.retrieve(query=query, limit=limit)
        avoided = self.retrieve(query=query, limit=3, include_rejected=True)
        if not context and not avoided:
            return ""
        lines: list[str] = []
        for item in context:
            layer = str(item.get("layer", "memory"))
            lines.append(f"- [{layer}] {item.get('summary') or item.get('content')}")
        rejected = [
            item
            for item in avoided
            if str(item.get("layer", "")) == "rejected_patterns"
        ]
        if rejected:
            lines.append("- [rejected_patterns] Avoid reusing previously rejected or unstable paths.")
            for item in rejected[:2]:
                lines.append(f"- [avoid] {item.get('summary') or item.get('content')}")
        return "\n".join(lines)

    def facts_payload(self) -> list[dict[str, str]]:
        facts: list[dict[str, str]] = []
        for item in self.retrieve(limit=12):
            facts.append(
                {
                    "category": str(item.get("type", "")),
                    "value": str(item.get("content", "")),
                    "layer": str(item.get("layer", "")),
                    "status": str(item.get("status", "")),
                }
            )
        return facts
