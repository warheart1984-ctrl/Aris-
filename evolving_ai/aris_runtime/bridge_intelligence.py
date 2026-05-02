from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
import hashlib
import json
import math
from pathlib import Path
import re
from typing import Any, Iterable

from evolving_ai.aris.memory_bank import GovernedMemoryBank


_HIGH_LEVEL_INTENTS = (
    "refactor",
    "feature",
    "bugfix",
    "inspect",
    "approval",
    "validation",
    "orchestration",
    "runtime_update",
    "general",
)

_SEMANTIC_INTENTS = (
    "compute",
    "control_flow",
    "state_update",
    "io_output",
    "io_input",
    "invoke",
    "transform",
    "validate",
    "manage_resource",
    "delete",
    "orchestrate",
)

_RISK_LEVELS = ("low", "medium", "high", "critical")

_TASK_MEMORY_TEMPLATE = {
    "task_id": "",
    "title": "",
    "goals": [],
    "constraints": [],
    "notes": [],
    "do_not_touch": [],
    "reject_reasons": [],
    "intent_history": [],
    "risk_history": [],
    "affected_modules": [],
    "updated_at": "",
}


def _utc_now() -> str:
    return datetime.now(UTC).replace(microsecond=0).isoformat()


def _clean(value: object) -> str:
    return re.sub(r"\s+", " ", str(value or "").strip())


def _slug(value: object) -> str:
    text = "".join(char.lower() if str(char).isalnum() else "-" for char in _clean(value))
    collapsed = "-".join(part for part in text.split("-") if part)
    return collapsed or "item"


def _hash(value: object) -> str:
    return hashlib.sha256(str(value).encode("utf-8")).hexdigest()


def _read_json(path: Path, default: Any) -> Any:
    if not path.exists():
        return default
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return default


def _write_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, ensure_ascii=True) + "\n", encoding="utf-8")


def _dict(value: object) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


def _changed_modules(files: Iterable[str]) -> list[str]:
    modules: set[str] = set()
    for file_path in files:
        normalized = str(file_path).replace("\\", "/").strip("/")
        if not normalized:
            continue
        parts = [part for part in normalized.split("/") if part]
        if len(parts) >= 2:
            if parts[0] in {"evolving_ai", "src", "tests", "forge", "forge_eval"}:
                modules.add(parts[1] if len(parts) > 1 else parts[0])
            else:
                modules.add(parts[0])
        elif parts:
            modules.add(parts[0])
    return sorted(module for module in modules if module)


def _event_text(event: dict[str, Any]) -> str:
    pieces = [
        _clean(event.get("title", "")),
        _clean(event.get("summary", "")),
        _clean(event.get("detail", "")),
        _clean(event.get("message", "")),
        _clean(event.get("content", "")),
        _clean(event.get("kind", "")),
    ]
    return " ".join(piece for piece in pieces if piece).strip()


def _high_level_intent(text: str, *, files: Iterable[str] = ()) -> str:
    normalized = text.lower()
    joined_files = " ".join(str(item).lower() for item in files)
    if any(token in normalized for token in ("refactor", "rename", "cleanup", "tighten", "simplify")):
        return "refactor"
    if any(token in normalized for token in ("fix", "bug", "repair", "patch")):
        return "bugfix"
    if any(token in normalized for token in ("inspect", "analy", "review", "summarize", "trace")):
        return "inspect"
    if any(token in normalized for token in ("approve", "approval", "reject", "review gate")):
        return "approval"
    if any(token in normalized for token in ("test", "verify", "validation", "check")):
        return "validation"
    if any(token in normalized for token in ("route", "queue", "orchestr", "schedule")):
        return "orchestration"
    if any(token in normalized for token in ("add", "create", "build", "implement", "feature")):
        return "feature"
    if "runtime" in normalized or "runtime" in joined_files:
        return "runtime_update"
    return "general"


def _semantic_intent_from_high_level(intent: str) -> str:
    mapping = {
        "refactor": "transform",
        "feature": "manage_resource",
        "bugfix": "state_update",
        "inspect": "io_input",
        "approval": "validate",
        "validation": "validate",
        "orchestration": "orchestrate",
        "runtime_update": "state_update",
        "general": "invoke",
    }
    return mapping.get(intent, "invoke")


def _infer_domain(files: Iterable[str], text: str) -> str:
    normalized_text = text.lower()
    for file_path in files:
        normalized = str(file_path).replace("\\", "/").lower()
        if "/runtime" in normalized or normalized.endswith("runtime.py"):
            return "runtime"
        if "/config" in normalized or "config" in normalized:
            return "config"
        if normalized.startswith("tests/") or "/tests/" in normalized:
            return "repo"
        if normalized.startswith("src/") or normalized.startswith("evolving_ai/"):
            return "repo"
    if any(token in normalized_text for token in ("network", "http", "api")):
        return "network"
    if any(token in normalized_text for token in ("memory", "task memory", "notes")):
        return "memory"
    return "unknown"


def _infer_operation(intent: str, text: str) -> str:
    normalized_text = text.lower()
    if intent in {"inspect", "validation"}:
        return "read" if intent == "inspect" else "compare"
    if any(token in normalized_text for token in ("delete", "remove", "purge")):
        return "delete"
    if any(token in normalized_text for token in ("branch", "fork")):
        return "branch"
    if any(token in normalized_text for token in ("execute", "run", "launch")):
        return "execute"
    if any(token in normalized_text for token in ("create", "add")):
        return "create"
    if any(token in normalized_text for token in ("update", "change", "modify", "patch", "fix", "refactor")):
        return "update"
    return "call"


def _infer_effect(operation: str) -> str:
    if operation in {"read", "compare"}:
        return "read"
    if operation in {"delete"}:
        return "delete"
    if operation in {"update", "create", "write", "branch"}:
        return "write"
    if operation in {"execute", "call"}:
        return "side_effect"
    return "none"


def _risk_from_context(*, files: Iterable[str], text: str, approval_required: bool = False) -> str:
    normalized_text = text.lower()
    file_list = [str(item).replace("\\", "/").lower() for item in files]
    if approval_required:
        return "high"
    if any(token in normalized_text for token in ("delete", "remove", "purge", "override", "bypass", "rewrite law")):
        return "critical"
    if any(
        token in normalized_text
        for token in ("runtime", "law", "kill switch", "integrity", "protected", "approval", "forge eval")
    ):
        return "high"
    if any(
        any(marker in path for marker in ("/runtime", "/shield", "/law", "/integrity", "/kill_switch"))
        for path in file_list
    ):
        return "high"
    if any(any(marker in path for marker in ("/config", "/server", "/service")) for path in file_list):
        return "medium"
    return "low"


def _confidence(intent: str, risk: str, *, occurrences: int = 0) -> float:
    base = {
        "inspect": 0.82,
        "validation": 0.8,
        "approval": 0.78,
        "refactor": 0.74,
        "bugfix": 0.72,
        "feature": 0.7,
        "orchestration": 0.68,
        "runtime_update": 0.65,
        "general": 0.6,
    }.get(intent, 0.6)
    risk_penalty = {"low": 0.0, "medium": 0.05, "high": 0.11, "critical": 0.18}.get(risk, 0.0)
    experience_bonus = min(0.12, occurrences * 0.01)
    return max(0.1, min(0.96, base - risk_penalty + experience_bonus))


def _semantic_token(event: dict[str, Any]) -> str:
    outcome = str(event.get("outcome", "")).strip().lower()
    if outcome in {"failure", "blocked"}:
        return outcome
    return str(event.get("intent", "invoke")).strip().lower() or "invoke"


@dataclass(slots=True)
class SemanticEvent:
    actor: str
    intent: str
    high_level_intent: str
    domain: str
    operation: str
    risk: str
    effect: str
    outcome: str
    context: dict[str, Any]
    provenance: dict[str, Any]
    ts: str

    def payload(self) -> dict[str, Any]:
        return {
            "actor": self.actor,
            "intent": self.intent,
            "high_level_intent": self.high_level_intent,
            "domain": self.domain,
            "operation": self.operation,
            "risk": self.risk,
            "effect": self.effect,
            "outcome": self.outcome,
            "context": self.context,
            "provenance": self.provenance,
            "ts": self.ts,
        }


class TaskMemoryStore:
    def __init__(self, path: Path, *, memory_bank: GovernedMemoryBank | None = None) -> None:
        self.path = path.resolve()
        self.memory_bank = memory_bank
        if not self.path.exists():
            _write_json(self.path, {})

    def _read_all(self) -> dict[str, dict[str, Any]]:
        payload = _read_json(self.path, {})
        return payload if isinstance(payload, dict) else {}

    def _write_all(self, payload: dict[str, dict[str, Any]]) -> None:
        _write_json(self.path, payload)

    def get(self, task_id: str, *, title: str = "") -> dict[str, Any]:
        key = _clean(task_id)
        payload = self._read_all()
        record = dict(_TASK_MEMORY_TEMPLATE)
        record.update(payload.get(key, {}))
        record["task_id"] = key
        if title and not record.get("title"):
            record["title"] = _clean(title)
        if not record.get("updated_at"):
            record["updated_at"] = _utc_now()
        return record

    def update(
        self,
        task_id: str,
        *,
        title: str = "",
        goals: Iterable[str] | None = None,
        constraints: Iterable[str] | None = None,
        notes: Iterable[str] | None = None,
        do_not_touch: Iterable[str] | None = None,
    ) -> dict[str, Any]:
        key = _clean(task_id)
        payload = self._read_all()
        record = self.get(key, title=title)
        if title:
            record["title"] = _clean(title)
        if goals is not None:
            record["goals"] = [_clean(item) for item in goals if _clean(item)]
        if constraints is not None:
            record["constraints"] = [_clean(item) for item in constraints if _clean(item)]
        if notes is not None:
            record["notes"] = [_clean(item) for item in notes if _clean(item)]
        if do_not_touch is not None:
            record["do_not_touch"] = [_clean(item) for item in do_not_touch if _clean(item)]
        record["updated_at"] = _utc_now()
        payload[key] = record
        self._write_all(payload)
        self._mirror_to_memory_bank(record)
        return record

    def record_intelligence(
        self,
        task_id: str,
        *,
        title: str = "",
        intent: str,
        risk: str,
        affected_modules: Iterable[str] = (),
    ) -> dict[str, Any]:
        record = self.get(task_id, title=title)
        if title:
            record["title"] = _clean(title)
        if intent:
            history = [str(item) for item in list(record.get("intent_history", []))]
            if intent not in history:
                history.append(intent)
            record["intent_history"] = history[-8:]
        if risk:
            risk_history = [str(item) for item in list(record.get("risk_history", []))]
            if risk not in risk_history:
                risk_history.append(risk)
            record["risk_history"] = risk_history[-8:]
        modules = sorted(
            {str(item).strip() for item in list(record.get("affected_modules", [])) + list(affected_modules) if str(item).strip()}
        )
        record["affected_modules"] = modules
        record["updated_at"] = _utc_now()
        payload = self._read_all()
        payload[_clean(task_id)] = record
        self._write_all(payload)
        return record

    def record_reject_reason(
        self,
        task_id: str,
        *,
        title: str = "",
        reason: str,
        note: str = "",
        intent: str = "",
        risk: str = "",
        affected_modules: Iterable[str] = (),
    ) -> dict[str, Any]:
        record = self.record_intelligence(
            task_id,
            title=title,
            intent=intent,
            risk=risk,
            affected_modules=affected_modules,
        )
        reject_reasons = [dict(item) for item in list(record.get("reject_reasons", [])) if isinstance(item, dict)]
        reject_reasons.append(
            {
                "reason": _clean(reason) or "Rejected by operator",
                "note": _clean(note),
                "timestamp": _utc_now(),
            }
        )
        record["reject_reasons"] = reject_reasons[-12:]
        record["updated_at"] = _utc_now()
        payload = self._read_all()
        payload[_clean(task_id)] = record
        self._write_all(payload)
        self._mirror_to_memory_bank(record)
        return record

    def prompt_context(self, task_id: str) -> list[str]:
        record = self.get(task_id)
        lines: list[str] = []
        if record.get("goals"):
            lines.append("Goals: " + "; ".join(str(item) for item in record["goals"]))
        if record.get("constraints"):
            lines.append("Constraints: " + "; ".join(str(item) for item in record["constraints"]))
        if record.get("do_not_touch"):
            lines.append("Do not touch: " + "; ".join(str(item) for item in record["do_not_touch"]))
        if record.get("notes"):
            lines.append("Notes: " + "; ".join(str(item) for item in record["notes"][:3]))
        if record.get("reject_reasons"):
            latest = record["reject_reasons"][-1]
            reason = _clean(latest.get("reason", ""))
            note = _clean(latest.get("note", ""))
            if reason:
                lines.append(
                    "Avoid previous rejection pattern: "
                    + reason
                    + (f" ({note})" if note else "")
                )
        return lines

    def _mirror_to_memory_bank(self, record: dict[str, Any]) -> None:
        if self.memory_bank is None:
            return
        task_id = _clean(record.get("task_id", ""))
        title = _clean(record.get("title", "")) or task_id
        chunks = []
        for field in ("goals", "constraints", "notes", "do_not_touch"):
            values = [str(item) for item in list(record.get(field, [])) if _clean(item)]
            if values:
                chunks.append(f"{field}: " + "; ".join(values))
        if record.get("reject_reasons"):
            latest = record["reject_reasons"][-1]
            chunks.append(
                "reject_reasons: "
                + _clean(latest.get("reason", ""))
                + (f" ({_clean(latest.get('note', ''))})" if _clean(latest.get("note", "")) else "")
            )
        if not chunks:
            return
        summary = f"Task memory for {title}"
        content = "\n".join(chunks)
        self.memory_bank.admit_entry(
            layer="operational",
            entry_type="task_memory",
            source="aris_runtime_desktop",
            summary=summary,
            content=content,
            tags=("task-memory", task_id, _slug(title)),
            status="active",
            entry_id=f"task-memory-{_slug(task_id)}",
        )


class PatternStore:
    def __init__(self, path: Path, *, memory_bank: GovernedMemoryBank | None = None) -> None:
        self.path = path.resolve()
        self.memory_bank = memory_bank
        if not self.path.exists():
            _write_json(self.path, {"patterns": {}, "ingested_trace_keys": []})

    def _payload(self) -> dict[str, Any]:
        payload = _read_json(self.path, {"patterns": {}, "ingested_trace_keys": []})
        if not isinstance(payload, dict):
            return {"patterns": {}, "ingested_trace_keys": []}
        if not isinstance(payload.get("patterns"), dict):
            payload["patterns"] = {}
        if not isinstance(payload.get("ingested_trace_keys"), list):
            payload["ingested_trace_keys"] = []
        return payload

    def _write(self, payload: dict[str, Any]) -> None:
        _write_json(self.path, payload)

    def _pattern_key(self, sequence: Iterable[str], modules: Iterable[str]) -> str:
        normalized = json.dumps(
            {
                "sequence": [str(item).strip() for item in sequence if str(item).strip()],
                "modules": sorted({str(item).strip() for item in modules if str(item).strip()}),
            },
            sort_keys=True,
        )
        return _hash(normalized)[:20]

    def ingest(
        self,
        *,
        trace_key: str,
        sequence: list[str],
        files: list[str],
        modules: list[str],
        tags: list[str],
        success: bool,
        retries: int,
        duration_ms: int,
        violations: list[str],
    ) -> dict[str, Any] | None:
        normalized_trace_key = _clean(trace_key)
        if not normalized_trace_key or not sequence:
            return None
        payload = self._payload()
        ingested = [str(item) for item in payload.get("ingested_trace_keys", [])]
        if normalized_trace_key in ingested:
            key = self._pattern_key(sequence, modules)
            return dict(payload.get("patterns", {}).get(key, {})) or None
        key = self._pattern_key(sequence, modules)
        existing = dict(payload.get("patterns", {}).get(key, {}))
        occurrences = max(0, int(existing.get("occurrences", 0))) + 1
        success_value = 1.0 if success else 0.0
        previous_success = float(_dict(existing.get("metrics")).get("successRate", success_value if success else 0.0))
        previous_retries = float(_dict(existing.get("metrics")).get("avgRetries", retries))
        previous_duration = float(_dict(existing.get("metrics")).get("avgDuration", duration_ms))
        success_rate = ((previous_success * (occurrences - 1)) + success_value) / occurrences
        avg_retries = ((previous_retries * (occurrences - 1)) + retries) / occurrences
        avg_duration = ((previous_duration * (occurrences - 1)) + duration_ms) / occurrences
        pattern = {
            "id": str(existing.get("id", f"pattern-{key}")),
            "sequence": [str(item).strip() for item in sequence if str(item).strip()],
            "context": {
                "files": sorted({str(item).strip() for item in files if str(item).strip()})[:12],
                "modules": sorted({str(item).strip() for item in modules if str(item).strip()}),
                "tags": sorted({str(item).strip() for item in tags if str(item).strip()}),
            },
            "outcome": {
                "success": bool(success),
                "retries": max(0, int(retries)),
                "durationMs": max(0, int(duration_ms)),
            },
            "metrics": {
                "successRate": round(success_rate, 4),
                "avgRetries": round(avg_retries, 4),
                "avgDuration": round(avg_duration, 2),
                "failureRate": round(1 - success_rate, 4),
            },
            "violations": {
                "count": max(0, int(_dict(existing.get("violations")).get("count", 0))) + len(violations),
                "rules": sorted({str(item).strip() for item in violations + list(_dict(existing.get("violations")).get("rules", [])) if str(item).strip()}),
            },
            "weight": round(min(24.0, float(existing.get("weight", 0.0)) + 1.0), 4),
            "lastSeen": _utc_now(),
            "occurrences": occurrences,
        }
        payload["patterns"][key] = pattern
        ingested.append(normalized_trace_key)
        payload["ingested_trace_keys"] = ingested[-500:]
        self._write(payload)
        self._mirror_to_memory_bank(pattern)
        return pattern

    def list_patterns(self, *, limit: int = 50) -> list[dict[str, Any]]:
        payload = self._payload()
        patterns = [dict(item) for item in payload.get("patterns", {}).values() if isinstance(item, dict)]
        now = datetime.now(UTC)
        for pattern in patterns:
            age_days = 0.0
            try:
                age_days = max(
                    0.0,
                    (now - datetime.fromisoformat(str(pattern.get("lastSeen", _utc_now())))).total_seconds() / 86400.0,
                )
            except ValueError:
                age_days = 0.0
            decay = math.exp(-age_days / 7.0)
            pattern["decayed_weight"] = round(float(pattern.get("weight", 1.0)) * decay, 4)
        patterns.sort(
            key=lambda item: (
                -float(item.get("decayed_weight", item.get("weight", 0.0))),
                -float(_dict(item.get("metrics")).get("successRate", 0.0)),
                -int(item.get("occurrences", 0)),
            )
        )
        return patterns[: max(1, limit)]

    def match(self, *, modules: Iterable[str], tags: Iterable[str], limit: int = 6) -> list[dict[str, Any]]:
        module_set = {str(item).strip().lower() for item in modules if str(item).strip()}
        tag_set = {str(item).strip().lower() for item in tags if str(item).strip()}
        matches: list[tuple[float, dict[str, Any]]] = []
        for pattern in self.list_patterns(limit=250):
            context = _dict(pattern.get("context"))
            pattern_modules = {str(item).strip().lower() for item in list(context.get("modules", [])) if str(item).strip()}
            pattern_tags = {str(item).strip().lower() for item in list(context.get("tags", [])) if str(item).strip()}
            if module_set and not module_set.intersection(pattern_modules):
                if tag_set and not tag_set.intersection(pattern_tags):
                    continue
                if not tag_set:
                    continue
            score = self.score(pattern)
            matches.append((score, pattern))
        matches.sort(key=lambda item: (-item[0], -int(item[1].get("occurrences", 0))))
        return [dict(item) for _, item in matches[: max(1, limit)]]

    def score(self, pattern: dict[str, Any]) -> float:
        metrics = _dict(pattern.get("metrics"))
        success_rate = float(metrics.get("successRate", 0.0))
        avg_retries = min(5.0, max(0.0, float(metrics.get("avgRetries", 0.0))))
        failure_rate = float(metrics.get("failureRate", 1.0))
        return (
            success_rate * 0.6
            + (1 - avg_retries / 5.0) * 0.2
            + (1 - failure_rate) * 0.2
        )

    def risk(self, pattern: dict[str, Any]) -> float:
        metrics = _dict(pattern.get("metrics"))
        failure_rate = float(metrics.get("failureRate", 1.0))
        violation_count = int(_dict(pattern.get("violations")).get("count", 0))
        return min(1.0, failure_rate * 0.6 + (0.4 if violation_count > 0 else 0.0))

    def build_decision_intelligence(
        self,
        *,
        modules: Iterable[str],
        tags: Iterable[str],
        intent: str,
        risk: str,
    ) -> dict[str, Any]:
        matches = self.match(modules=modules, tags=tags, limit=4)
        if matches:
            top = matches[0]
            top_metrics = _dict(top.get("metrics"))
            occurrences = max(1, int(top.get("occurrences", 1)))
            mean = max(0.1, min(0.98, float(top_metrics.get("successRate", 0.6))))
            uncertainty = max(0.05, min(0.35, 1.0 / (occurrences + 2) + self.risk(top) * 0.2))
            alternative = matches[1] if len(matches) > 1 else None
        else:
            mean = _confidence(intent, risk)
            uncertainty = {"low": 0.09, "medium": 0.14, "high": 0.2, "critical": 0.28}.get(risk, 0.16)
            top = {
                "id": f"pattern-{_slug(intent)}",
                "sequence": [intent, "review", "outcome"],
                "context": {"modules": list(modules), "tags": list(tags)},
                "metrics": {"successRate": mean, "failureRate": 1 - mean},
                "occurrences": 0,
                "violations": {"count": 0, "rules": []},
            }
            alternative = None
        low = max(0.0, mean - uncertainty)
        high = min(1.0, mean + uncertainty)
        if alternative is not None:
            alt_metrics = _dict(alternative.get("metrics"))
            alt_mean = max(0.05, min(0.98, float(alt_metrics.get("successRate", mean))))
            alt_uncertainty = max(0.05, min(0.35, 1.0 / (max(1, int(alternative.get("occurrences", 1))) + 2) + self.risk(alternative) * 0.2))
            reason = (
                "Lower uncertainty and fewer failure chains."
                if uncertainty <= alt_uncertainty
                else "Higher historical success outweighed the safer alternative."
            )
        else:
            alt_mean = max(0.05, min(0.98, mean - 0.04))
            alt_uncertainty = min(0.4, uncertainty + 0.06)
            reason = "No stronger matched pattern exists yet, so ARIS is using the most stable available path."
        strategy_origin = "pattern" if matches else "mutation"
        mutations: list[str] = []
        if risk in {"high", "critical"}:
            mutations.append("reduce_scope")
        if intent in {"bugfix", "refactor"}:
            mutations.append("add_validation")
        if not mutations:
            mutations.append("stabilize_route")
        return {
            "chain": {
                "mean": round(mean, 4),
                "low": round(low, 4),
                "high": round(high, 4),
                "uncertainty": round(uncertainty, 4),
                "steps": list(top.get("sequence", []))[:5],
            },
            "counterfactual": {
                "altMean": round(alt_mean, 4),
                "altLow": round(max(0.0, alt_mean - alt_uncertainty), 4),
                "altHigh": round(min(1.0, alt_mean + alt_uncertainty), 4),
                "reason": reason,
            },
            "strategy": {
                "id": f"{intent}_strategy",
                "generation": max(1, int(top.get("occurrences", 0)) + 1),
                "origin": strategy_origin,
                "mutations": mutations[:3],
                "parentIds": [str(top.get("id", ""))] if str(top.get("id", "")) else [],
            },
            "matches": matches,
        }

    def _mirror_to_memory_bank(self, pattern: dict[str, Any]) -> None:
        if self.memory_bank is None:
            return
        summary = (
            f"Pattern {pattern.get('id', '')}: "
            + " -> ".join(str(item) for item in list(pattern.get("sequence", []))[:5])
        )
        content = json.dumps(pattern, ensure_ascii=True)
        layer = "learned_patterns"
        if self.risk(pattern) > 0.6:
            layer = "rejected_patterns"
        self.memory_bank.admit_entry(
            layer=layer,
            entry_type="bridge_pattern",
            source="aris_runtime_bridge",
            summary=summary,
            content=content,
            tags=("pattern", layer, _slug(pattern.get("id", ""))),
            status="admitted" if layer == "learned_patterns" else "rejected",
            entry_id=f"{layer}-{_slug(pattern.get('id', 'pattern'))}",
        )


class BranchReplayStore:
    def __init__(self, path: Path) -> None:
        self.path = path.resolve()
        if not self.path.exists():
            _write_json(self.path, {"branches": [], "seen_keys": []})

    def _payload(self) -> dict[str, Any]:
        payload = _read_json(self.path, {"branches": [], "seen_keys": []})
        if not isinstance(payload, dict):
            return {"branches": [], "seen_keys": []}
        if not isinstance(payload.get("branches"), list):
            payload["branches"] = []
        if not isinstance(payload.get("seen_keys"), list):
            payload["seen_keys"] = []
        return payload

    def record_branch(
        self,
        *,
        branch_key: str,
        task_id: str,
        run_id: str,
        title: str,
        state: str,
        reason: str,
        intent: str,
        risk: str,
        changed_files: Iterable[str],
        affected_modules: Iterable[str],
    ) -> dict[str, Any] | None:
        normalized_key = _clean(branch_key)
        if not normalized_key:
            return None
        payload = self._payload()
        seen_keys = [str(item) for item in payload.get("seen_keys", [])]
        if normalized_key in seen_keys:
            for branch in payload.get("branches", []):
                if isinstance(branch, dict) and str(branch.get("branch_key", "")).strip() == normalized_key:
                    return dict(branch)
            return None
        branch = {
            "branch_id": f"branch-{_hash(normalized_key)[:12]}",
            "branch_key": normalized_key,
            "task_id": _clean(task_id),
            "run_id": _clean(run_id),
            "title": _clean(title) or "Task branch",
            "state": _clean(state) or "review",
            "reason": _clean(reason) or "Branch recorded from governed run state.",
            "intent": _clean(intent) or "general",
            "risk": _clean(risk) or "low",
            "changed_files": sorted({str(item).strip() for item in changed_files if str(item).strip()}),
            "affected_modules": sorted({str(item).strip() for item in affected_modules if str(item).strip()}),
            "created_at": _utc_now(),
        }
        branches = [dict(item) for item in payload.get("branches", []) if isinstance(item, dict)]
        branches.append(branch)
        payload["branches"] = branches[-200:]
        seen_keys.append(normalized_key)
        payload["seen_keys"] = seen_keys[-500:]
        _write_json(self.path, payload)
        return branch

    def list_branches(self, *, task_id: str = "", run_id: str = "", limit: int = 10) -> list[dict[str, Any]]:
        payload = self._payload()
        branches = [dict(item) for item in payload.get("branches", []) if isinstance(item, dict)]
        filtered: list[dict[str, Any]] = []
        for branch in reversed(branches):
            if task_id and str(branch.get("task_id", "")).strip() != _clean(task_id):
                continue
            if run_id and str(branch.get("run_id", "")).strip() != _clean(run_id):
                continue
            filtered.append(branch)
            if len(filtered) >= max(1, limit):
                break
        return filtered

    def build_replay(
        self,
        *,
        task: dict[str, Any] | None,
        run: dict[str, Any] | None,
        run_events: Iterable[dict[str, Any]],
        local_events: Iterable[dict[str, Any]],
    ) -> dict[str, Any]:
        timeline: list[dict[str, Any]] = []
        sequence = 0
        for event in list(run_events):
            if not isinstance(event, dict):
                continue
            sequence += 1
            timeline.append(
                {
                    "seq": sequence,
                    "scope": "run",
                    "time": _clean(event.get("created_at") or event.get("timestamp") or event.get("time")),
                    "label": _clean(event.get("kind") or event.get("title") or event.get("event")),
                    "detail": _event_text(event),
                }
            )
        for event in list(local_events)[:10]:
            if not isinstance(event, dict):
                continue
            sequence += 1
            timeline.append(
                {
                    "seq": sequence,
                    "scope": "runtime",
                    "time": _clean(event.get("timestamp") or event.get("time")),
                    "label": _clean(event.get("kind") or event.get("title")),
                    "detail": _clean(event.get("detail")),
                }
            )
        title = _clean(_dict(task).get("title") or _dict(run).get("title") or _dict(run).get("user_message"))
        return {
            "title": title or "Replay",
            "cursor_max": len(timeline),
            "timeline": timeline[-40:],
            "summary": (
                f"{title or 'Run'} captured {len(timeline)} replay step(s)."
                if timeline
                else "No replay steps are available yet."
            ),
        }


class BridgeIntelligenceEngine:
    def __init__(self, root: Path, *, memory_bank: GovernedMemoryBank | None = None) -> None:
        self.root = root.resolve()
        self.root.mkdir(parents=True, exist_ok=True)
        self.memory_bank = memory_bank
        self.task_memory = TaskMemoryStore(self.root / "task-memory.json", memory_bank=memory_bank)
        self.pattern_store = PatternStore(self.root / "pattern-store.json", memory_bank=memory_bank)
        self.branch_store = BranchReplayStore(self.root / "branches.json")

    def build_for_task(
        self,
        *,
        task: dict[str, Any] | None,
        review: dict[str, Any] | None,
        run: dict[str, Any] | None = None,
        run_events: Iterable[dict[str, Any]] = (),
        local_events: Iterable[dict[str, Any]] = (),
    ) -> dict[str, Any]:
        task_payload = dict(task or {})
        review_payload = dict(review or {})
        run_payload = dict(run or {})
        changed_files = [str(item).strip() for item in list(review_payload.get("changed_files", [])) if str(item).strip()]
        if not changed_files:
            changed_files = [
                str(_dict(item).get("path", "")).strip()
                for item in list(review_payload.get("changed_entries", []))
                if isinstance(item, dict) and str(item.get("path", "")).strip()
            ]
        changed_files = [item for item in changed_files if item]
        affected_modules = _changed_modules(changed_files)
        task_text = " ".join(
            [
                _clean(task_payload.get("title", "")),
                _clean(task_payload.get("summary", "")),
                _clean(task_payload.get("latest_update", "")),
                _clean(review_payload.get("summary", "")),
                " ".join(_event_text(event) for event in list(run_events)[-10:] if isinstance(event, dict)),
            ]
        ).strip()
        approval_required = bool(_clean(task_payload.get("approval_id", ""))) or _clean(task_payload.get("review_gate", "")) == "operator_review"
        intent = _high_level_intent(task_text, files=changed_files)
        semantic_intent = _semantic_intent_from_high_level(intent)
        domain = _infer_domain(changed_files, task_text)
        operation = _infer_operation(intent, task_text)
        effect = _infer_effect(operation)
        risk = _risk_from_context(files=changed_files, text=task_text, approval_required=approval_required)
        memory = self.task_memory.record_intelligence(
            _clean(task_payload.get("id", "") or run_payload.get("id", "") or task_payload.get("title", "scratchpad")),
            title=_clean(task_payload.get("title", "") or run_payload.get("title", "")),
            intent=intent,
            risk=risk,
            affected_modules=affected_modules,
        )
        semantic_events = self._semantic_events(
            task=task_payload,
            run=run_payload,
            run_events=list(run_events),
            changed_files=changed_files,
            intent=intent,
            semantic_intent=semantic_intent,
            domain=domain,
            operation=operation,
            effect=effect,
            risk=risk,
        )
        self._maybe_ingest_pattern(
            task=task_payload,
            run=run_payload,
            semantic_events=semantic_events,
            changed_files=changed_files,
            affected_modules=affected_modules,
            intent=intent,
            risk=risk,
        )
        decision = self.pattern_store.build_decision_intelligence(
            modules=affected_modules,
            tags=[intent, risk, domain],
            intent=intent,
            risk=risk,
        )
        replay = self.branch_store.build_replay(
            task=task_payload,
            run=run_payload,
            run_events=run_events,
            local_events=local_events,
        )
        branch = self._maybe_record_branch(
            task=task_payload,
            run=run_payload,
            review=review_payload,
            intent=intent,
            risk=risk,
            affected_modules=affected_modules,
            changed_files=changed_files,
            semantic_events=semantic_events,
        )
        branches = self.branch_store.list_branches(
            task_id=_clean(task_payload.get("id", "")),
            run_id=_clean(run_payload.get("id", "")),
            limit=8,
        )
        confidence = _confidence(intent, risk, occurrences=max(0, int(decision.get("strategy", {}).get("generation", 1)) - 1))
        approval_summary = {
            "summary": self._approval_summary(
                title=_clean(task_payload.get("title", "") or run_payload.get("title", "")),
                review=review_payload,
                intent=intent,
                risk=risk,
                affected_modules=affected_modules,
                changed_files=changed_files,
            ),
            "intent": intent,
            "semantic_intent": semantic_intent,
            "risk": risk,
            "affected_modules": affected_modules,
            "changed_files": changed_files,
            "change_count": len(changed_files),
            "recommendation": (
                "Inspect the diff before approval."
                if risk in {"high", "critical"} or changed_files
                else "Ready for governed review."
            ),
        }
        return {
            "intent": intent,
            "semantic_intent": semantic_intent,
            "risk": risk,
            "confidence": round(confidence, 4),
            "domain": domain,
            "operation": operation,
            "effect": effect,
            "affected_modules": affected_modules,
            "changed_files": changed_files,
            "semantic_events": [event.payload() for event in semantic_events[-10:]],
            "task_memory": memory,
            "approval_summary": approval_summary,
            "decision": decision,
            "replay": replay,
            "branches": branches,
            "latest_branch": branch,
        }

    def save_task_memory(
        self,
        *,
        task_id: str,
        title: str = "",
        goals: Iterable[str] | None = None,
        constraints: Iterable[str] | None = None,
        notes: Iterable[str] | None = None,
        do_not_touch: Iterable[str] | None = None,
    ) -> dict[str, Any]:
        return self.task_memory.update(
            task_id,
            title=title,
            goals=goals,
            constraints=constraints,
            notes=notes,
            do_not_touch=do_not_touch,
        )

    def record_rejection(
        self,
        *,
        task_id: str,
        title: str = "",
        reason: str,
        note: str = "",
        intelligence: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        payload = dict(intelligence or {})
        intent = _clean(payload.get("intent", ""))
        risk = _clean(payload.get("risk", ""))
        affected_modules = [
            str(item).strip()
            for item in list(payload.get("affected_modules", []))
            if str(item).strip()
        ]
        record = self.task_memory.record_reject_reason(
            task_id,
            title=title,
            reason=reason,
            note=note,
            intent=intent,
            risk=risk,
            affected_modules=affected_modules,
        )
        if self.memory_bank is not None:
            self.memory_bank.reject_pattern(
                name="operator_rejection",
                summary=f"Rejected path for {title or task_id}: {reason}",
                content=json.dumps(
                    {
                        "task_id": task_id,
                        "title": title,
                        "reason": reason,
                        "note": note,
                        "intelligence": payload,
                    },
                    ensure_ascii=True,
                ),
                source="aris_runtime_desktop",
                tags=("operator-rejection", _slug(task_id), _slug(reason)),
            )
        return record

    def _approval_summary(
        self,
        *,
        title: str,
        review: dict[str, Any],
        intent: str,
        risk: str,
        affected_modules: list[str],
        changed_files: list[str],
    ) -> str:
        summary = _clean(review.get("summary", "")) or "No change summary is available yet."
        modules = ", ".join(affected_modules[:6]) if affected_modules else "no modules detected"
        files = ", ".join(Path(path).name for path in changed_files[:4]) if changed_files else "no changed files detected"
        return (
            f"{summary}\n"
            f"Intent: {intent.title()} • Risk: {risk.title()}\n"
            f"Affected modules: {modules}\n"
            f"Changed files: {files}"
        )

    def _semantic_events(
        self,
        *,
        task: dict[str, Any],
        run: dict[str, Any],
        run_events: list[dict[str, Any]],
        changed_files: list[str],
        intent: str,
        semantic_intent: str,
        domain: str,
        operation: str,
        effect: str,
        risk: str,
    ) -> list[SemanticEvent]:
        actor = _clean(run.get("actor", "") or task.get("source", "") or "aris")
        events: list[SemanticEvent] = []
        if run_events:
            for event in run_events[-12:]:
                if not isinstance(event, dict):
                    continue
                text = _event_text(event)
                if not text:
                    continue
                event_intent = _high_level_intent(text, files=changed_files)
                event_semantic = _semantic_intent_from_high_level(event_intent)
                event_operation = _infer_operation(event_intent, text)
                kind = _clean(event.get("kind", "")).lower()
                outcome = "success"
                if "fail" in text.lower() or kind in {"error", "failed"}:
                    outcome = "failure"
                elif "reject" in text.lower():
                    outcome = "blocked"
                elif "retry" in text.lower():
                    outcome = "retry"
                elif "skip" in text.lower():
                    outcome = "skipped"
                elif "approval" in text.lower() or kind == "approval_required":
                    outcome = "blocked"
                events.append(
                    SemanticEvent(
                        actor=actor,
                        intent=event_semantic,
                        high_level_intent=event_intent,
                        domain=_infer_domain(changed_files, text),
                        operation=event_operation,
                        risk=_risk_from_context(files=changed_files, text=text, approval_required="approval" in text.lower()),
                        effect=_infer_effect(event_operation),
                        outcome=outcome,
                        context={
                            "files": changed_files[:8],
                            "module": _changed_modules(changed_files)[0] if _changed_modules(changed_files) else "",
                            "verb": kind,
                        },
                        provenance={"source": "substrate", "capability": risk},
                        ts=_clean(event.get("created_at") or event.get("timestamp") or _utc_now()),
                    )
                )
        if not events:
            status = _clean(task.get("status", "pending")).lower() or "pending"
            outcome = "success" if status == "done" else "blocked" if status == "blocked" else "retry" if status == "pending" else "failure"
            events.append(
                SemanticEvent(
                    actor=actor,
                    intent=semantic_intent,
                    high_level_intent=intent,
                    domain=domain,
                    operation=operation,
                    risk=risk,
                    effect=effect,
                    outcome=outcome,
                    context={"files": changed_files[:8], "module": _changed_modules(changed_files)[0] if _changed_modules(changed_files) else "", "verb": status},
                    provenance={"source": "runtime", "capability": risk},
                    ts=_utc_now(),
                )
            )
        return events

    def _maybe_ingest_pattern(
        self,
        *,
        task: dict[str, Any],
        run: dict[str, Any],
        semantic_events: list[SemanticEvent],
        changed_files: list[str],
        affected_modules: list[str],
        intent: str,
        risk: str,
    ) -> None:
        task_id = _clean(task.get("id", "") or run.get("id", "") or task.get("title", "scratchpad"))
        if not task_id:
            return
        run_status = _clean(run.get("status", "") or task.get("status", ""))
        if not run_status:
            return
        trace_key = (
            f"{task_id}:{run_status}:{_hash(json.dumps([event.payload() for event in semantic_events], ensure_ascii=True))[:12]}"
        )
        retries = sum(1 for event in semantic_events if event.outcome in {"failure", "retry"})
        success = run_status.lower() in {"done", "completed"} or semantic_events[-1].outcome == "success"
        start_text = _clean(task.get("created_at") or run.get("created_at"))
        end_text = _clean(task.get("updated_at") or run.get("updated_at"))
        duration_ms = 0
        try:
            if start_text and end_text:
                duration_ms = int(
                    max(
                        0.0,
                        (
                            datetime.fromisoformat(end_text).timestamp()
                            - datetime.fromisoformat(start_text).timestamp()
                        )
                        * 1000.0,
                    )
                )
        except ValueError:
            duration_ms = 0
        violations = []
        if risk in {"high", "critical"} and not success:
            violations.append("high_risk_path_unresolved")
        self.pattern_store.ingest(
            trace_key=trace_key,
            sequence=[_semantic_token(event.payload()) for event in semantic_events[-5:]],
            files=changed_files,
            modules=affected_modules,
            tags=[intent, risk],
            success=success,
            retries=retries,
            duration_ms=duration_ms,
            violations=violations,
        )

    def _maybe_record_branch(
        self,
        *,
        task: dict[str, Any],
        run: dict[str, Any],
        review: dict[str, Any],
        intent: str,
        risk: str,
        affected_modules: list[str],
        changed_files: list[str],
        semantic_events: list[SemanticEvent],
    ) -> dict[str, Any] | None:
        task_id = _clean(task.get("id", ""))
        if not task_id:
            return None
        run_id = _clean(run.get("id", "") or task.get("linked_run_id", "") or task.get("run_id", ""))
        state = _clean(task.get("status", "") or run.get("status", "")).lower() or "pending"
        approval_id = _clean(task.get("approval_id", "") or run.get("blocked_on_approval_id", ""))
        should_branch = state in {"blocked", "done", "error"} or bool(approval_id)
        if not should_branch:
            return None
        reason = (
            "Approval review is required before continuation."
            if approval_id
            else _clean(task.get("latest_update", "") or review.get("summary", "") or state)
        )
        branch_key = f"{task_id}:{run_id}:{state}:{approval_id}:{_hash(json.dumps([event.payload() for event in semantic_events[-3:]], ensure_ascii=True))[:10]}"
        return self.branch_store.record_branch(
            branch_key=branch_key,
            task_id=task_id,
            run_id=run_id,
            title=_clean(task.get("title", "") or run.get("title", "")),
            state=state,
            reason=reason,
            intent=intent,
            risk=risk,
            changed_files=changed_files,
            affected_modules=affected_modules,
        )
