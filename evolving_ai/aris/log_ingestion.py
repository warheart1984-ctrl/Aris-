from __future__ import annotations

from datetime import UTC, datetime
import hashlib
import json
import re
from typing import Any
import uuid


def _utc_now() -> str:
    return datetime.now(UTC).isoformat()


def _normalize_text(value: Any) -> str:
    return re.sub(r"\s+", " ", str(value or "").strip())


def _json_hash(value: Any) -> str:
    return hashlib.sha256(
        json.dumps(value, sort_keys=True, ensure_ascii=True, separators=(",", ":")).encode("utf-8")
    ).hexdigest()


def _normalize_command(value: Any) -> list[str]:
    if isinstance(value, str):
        text = _normalize_text(value)
        return [text] if text else []
    if isinstance(value, (list, tuple, set)):
        return [_normalize_text(item) for item in value if _normalize_text(item)]
    return []


def _looks_like_code(text: str) -> bool:
    sample = str(text or "")
    if not sample.strip():
        return False
    markers = (
        "def ",
        "class ",
        "import ",
        "from ",
        "return ",
        "=",
        "if ",
        "for ",
        "while ",
    )
    return "\n" in sample or any(marker in sample for marker in markers)


def _extract_code_blocks(text: str) -> list[str]:
    blocks: list[str] = []
    for match in re.finditer(r"```(?:python)?\s*\n(.*?)```", str(text or ""), flags=re.IGNORECASE | re.DOTALL):
        block = str(match.group(1) or "").strip()
        if block:
            blocks.append(block)
    return blocks


def _normalize_action(action: Any, *, index: int) -> dict[str, Any]:
    if not isinstance(action, dict):
        return {
            "index": index,
            "type": "note",
            "file": "",
            "target": "",
            "value": _normalize_text(action),
            "command": [],
            "program": "",
            "patch": "",
        }
    action_type = _normalize_text(action.get("type")) or "unknown"
    target = _normalize_text(action.get("file") or action.get("path") or action.get("target"))
    value = _normalize_text(action.get("value") or action.get("summary"))
    command = _normalize_command(action.get("command") or action.get("value"))
    program = str(
        action.get("program")
        or action.get("code")
        or action.get("content")
        or action.get("after")
        or ""
    )
    patch = str(action.get("patch") or action.get("diff") or "")
    return {
        "index": index,
        "type": action_type,
        "file": target,
        "target": target,
        "value": value,
        "command": command,
        "program": program,
        "patch": patch,
    }


def normalize_codex_log(
    raw_log: Any,
    *,
    source: str = "codex",
    session_id: str = "codex-log",
) -> dict[str, Any]:
    task = ""
    result = "unknown"
    output_text = ""
    metadata: dict[str, Any] = {}
    actions: list[dict[str, Any]] = []

    if isinstance(raw_log, dict):
        task = _normalize_text(raw_log.get("task") or raw_log.get("goal") or raw_log.get("prompt"))
        result = _normalize_text(raw_log.get("result") or raw_log.get("status")) or "unknown"
        output_text = str(raw_log.get("output") or raw_log.get("stdout") or raw_log.get("response") or "")
        metadata = dict(raw_log.get("metadata") or {})
        actions = [
            _normalize_action(item, index=index)
            for index, item in enumerate(list(raw_log.get("actions") or []), start=1)
        ]
    else:
        output_text = str(raw_log or "")

    if not result:
        lowered = output_text.lower()
        if any(token in lowered for token in ("success", "passed", "done", "complete")):
            result = "success"
        elif any(token in lowered for token in ("error", "failed", "traceback")):
            result = "failure"
        else:
            result = "unknown"

    payload = {
        "packet_id": f"logpkt_{uuid.uuid4().hex[:12]}",
        "normalized_at": _utc_now(),
        "source": _normalize_text(source) or "codex",
        "session_id": _normalize_text(session_id) or "codex-log",
        "task": task or "Undeclared Codex log task.",
        "result": result,
        "action_count": len(actions),
        "actions": actions,
        "output_hash": hashlib.sha256(output_text.encode("utf-8")).hexdigest() if output_text else "",
        "output_excerpt": _normalize_text(output_text)[:240],
        "output_text": output_text,
        "metadata": metadata,
    }
    payload["trace_seed"] = _json_hash(
        {
            "source": payload["source"],
            "session_id": payload["session_id"],
            "task": payload["task"],
            "result": payload["result"],
            "actions": payload["actions"],
            "output_hash": payload["output_hash"],
        }
    )
    return payload


def extract_candidates(packet: dict[str, Any]) -> list[dict[str, Any]]:
    candidates: list[dict[str, Any]] = []
    for action in list(packet.get("actions") or []):
        target = _normalize_text(action.get("target"))
        patch = str(action.get("patch") or "")
        program = str(action.get("program") or "")
        if patch.strip():
            fingerprint = _json_hash({"kind": "patch", "target": target, "patch": patch})
            candidates.append(
                {
                    "candidate_id": f"cand_{fingerprint[:12]}",
                    "kind": "patch",
                    "target": target,
                    "program": "",
                    "patch": patch,
                    "source": packet.get("source"),
                    "context": packet.get("task"),
                    "fingerprint": fingerprint,
                    "extraction_source": f"action:{action.get('index')}",
                }
            )
            continue
        if _looks_like_code(program):
            fingerprint = _json_hash({"kind": "program", "target": target, "program": program})
            candidates.append(
                {
                    "candidate_id": f"cand_{fingerprint[:12]}",
                    "kind": "program",
                    "target": target,
                    "program": program,
                    "patch": "",
                    "source": packet.get("source"),
                    "context": packet.get("task"),
                    "fingerprint": fingerprint,
                    "extraction_source": f"action:{action.get('index')}",
                }
            )

    if candidates:
        return candidates

    for index, block in enumerate(_extract_code_blocks(str(packet.get("output_text") or "")), start=1):
        fingerprint = _json_hash({"kind": "program", "target": "", "program": block})
        candidates.append(
            {
                "candidate_id": f"cand_{fingerprint[:12]}",
                "kind": "program",
                "target": "",
                "program": block,
                "patch": "",
                "source": packet.get("source"),
                "context": packet.get("task"),
                "fingerprint": fingerprint,
                "extraction_source": f"output_code_block:{index}",
            }
        )
    return candidates


def build_forge_eval_request(candidate: dict[str, Any], *, repo_root: str) -> dict[str, Any]:
    lineage = str(candidate.get("fingerprint") or candidate.get("candidate_id") or "")
    target = _normalize_text(candidate.get("target"))
    if str(candidate.get("kind")) == "patch":
        return {
            "task_id": str(candidate.get("candidate_id") or ""),
            "mode": "repo_patch",
            "payload": {
                "patch": str(candidate.get("patch") or ""),
                "repo": repo_root,
                "lineage": lineage,
                "target": target,
                "diff_present": True,
                "test_result": "not_run",
                "config": {
                    "expected_files": [target] if target else [],
                },
            },
        }
    return {
        "task_id": str(candidate.get("candidate_id") or ""),
        "mode": "io_tests",
        "payload": {
            "program": str(candidate.get("program") or ""),
            "lineage": lineage,
            "target": target,
            "diff_present": False,
            "test_result": "not_run",
            "config": {
                "must_not_contain": [
                    "subprocess",
                    "socket",
                    "os.system",
                    "shutil.rmtree",
                    "eval(",
                    "exec(",
                ],
            },
        },
    }


def classify_evaluation(response_payload: dict[str, Any], *, status_code: int) -> dict[str, Any]:
    raw = dict(response_payload or {})
    result = dict(raw.get("result") or {})
    details = dict(result.get("details") or {})
    score = float(result.get("score", 0.0) or 0.0)
    violations = [dict(item) for item in list(details.get("violations") or []) if isinstance(item, dict)]
    checks = [dict(item) for item in list(details.get("checks") or []) if isinstance(item, dict)]
    failed_checks = [item for item in checks if not bool(item.get("passed", False))]
    if status_code != 200:
        return {
            "classification": "DISGRACE",
            "hall_name": "hall_of_discard",
            "reason": _normalize_text(raw.get("error", {}).get("message")) or "Forge Eval rejected the candidate.",
            "score": 0.0,
            "status_code": status_code,
            "violations": violations,
            "failed_checks": failed_checks,
            "raw": raw,
        }
    if violations or failed_checks:
        return {
            "classification": "DISGRACE",
            "hall_name": "hall_of_discard",
            "reason": "Forge Eval or Doc Channel violations blocked candidate admission.",
            "score": score,
            "status_code": status_code,
            "violations": violations,
            "failed_checks": failed_checks,
            "raw": raw,
        }
    if score >= 0.85:
        return {
            "classification": "FAME",
            "hall_name": "hall_of_fame",
            "reason": "Candidate met the Fame threshold under law.",
            "score": score,
            "status_code": status_code,
            "violations": violations,
            "failed_checks": failed_checks,
            "raw": raw,
        }
    return {
        "classification": "SHAME",
        "hall_name": "hall_of_shame",
        "reason": "Candidate remained below the Fame threshold and was preserved as non-live learning.",
        "score": score,
        "status_code": status_code,
        "violations": violations,
        "failed_checks": failed_checks,
        "raw": raw,
    }
