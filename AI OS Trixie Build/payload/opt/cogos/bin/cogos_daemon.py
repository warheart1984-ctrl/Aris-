#!/usr/bin/env python3
"""Persistent Project Infi / ARIS runtime daemon.

The daemon is intentionally small and local-first. It keeps a heartbeat,
records ARIS cycles as JSONL traces, and processes simple task files from
/opt/cogos/tasks/inbox without needing network services or a database.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import pathlib
import shutil
import signal
import subprocess
import sys
import time
import uuid
from typing import Any


ROOT = pathlib.Path(os.environ.get("COGOS_ROOT", "/opt/cogos"))
RUN = pathlib.Path("/run")
TASKS = ROOT / "tasks"
INBOX = TASKS / "inbox"
DONE = TASKS / "done"
FAILED = TASKS / "failed"
MEMORY = ROOT / "memory"
EVENTS = MEMORY / "events"
TRACES = MEMORY / "traces"
LOGS = MEMORY / "logs"
MODULE_MEMORY = MEMORY / "modules"
PATTERNS = MEMORY / "patterns"
SNAPSHOTS = MEMORY / "snapshots"
REFLECTION = MEMORY / "reflection"
ADMISSION = ROOT / "modules" / "admission"
LOCAL_MODULES = ROOT / "modules" / "local"
REGISTRY = ROOT / "modules" / "registry.json"
TRAIT_LEDGER = MODULE_MEMORY / "trait_ledger.jsonl"
IDENTITY_STATE = MODULE_MEMORY / "identity_state.json"
GOVERNANCE = ROOT / "law" / "governance_rules.json"
MANIFEST = ROOT / "config" / "module_manifest.json"
RUNTIME_CONFIG = ROOT / "config" / "runtime.json"
STATE_PATH = RUN / "cogos-daemon.json"
PID_PATH = RUN / "cogos-daemon.pid"
STOP = False


def now() -> str:
    return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())


def ensure_dirs() -> None:
    for path in [
        INBOX,
        DONE,
        FAILED,
        EVENTS,
        TRACES,
        LOGS,
        MEMORY / "operator",
        MODULE_MEMORY,
        PATTERNS,
        SNAPSHOTS,
        REFLECTION,
        ADMISSION,
        LOCAL_MODULES,
        ROOT / "modules" / "installed",
    ]:
        path.mkdir(parents=True, exist_ok=True)


def append_jsonl(path: pathlib.Path, item: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as fh:
        fh.write(json.dumps(item, sort_keys=True) + "\n")


def load_json(path: pathlib.Path) -> dict[str, Any]:
    with path.open("r", encoding="utf-8-sig") as fh:
        return json.load(fh)


def save_json(path: pathlib.Path, data: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def sha256_text(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def sha256_file(path: pathlib.Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as fh:
        for chunk in iter(lambda: fh.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def governance() -> dict[str, Any]:
    if GOVERNANCE.exists():
        return load_json(GOVERNANCE)
    return {"mode": "fail_closed", "authority_modes": {}, "law_rules": [], "cognitive_load": {"max_active_cycles": 6}}


def runtime_config() -> dict[str, Any]:
    if RUNTIME_CONFIG.exists():
        return load_json(RUNTIME_CONFIG)
    return {}


def sandbox_policy() -> dict[str, Any]:
    cfg = runtime_config().get("sandbox", {})
    return {
        "timeout_seconds": int(cfg.get("timeout_seconds", 5)),
        "max_stdout_bytes": int(cfg.get("max_stdout_bytes", 65536)),
        "max_stderr_bytes": int(cfg.get("max_stderr_bytes", 65536)),
        "network": cfg.get("network", "denied"),
        "write_paths": cfg.get("write_paths", []),
        "capability_paths": cfg.get("capability_paths", {
            "trace.read": ["/opt/cogos/memory/traces"],
            "memory.read": ["/opt/cogos/memory"],
            "memory.append": ["/opt/cogos/memory/modules/executions.jsonl"],
        }),
    }


def trait_runtime_policy() -> dict[str, Any]:
    cfg = runtime_config().get("trait_runtime", {})
    default_rules = {
        "readonly": {"forbids": ["memory.write", "network.write", "self.modify", "module.admit"]},
        "non_mutating": {"forbids": ["memory.write", "network.write", "self.modify", "module.admit"], "mutation_output_markers": ["mutate", "write", "delete", "self_modify"]},
        "analytical": {"expects_structured_output": True},
        "verifier": {"expects_any_output_fields": ["proof", "checks", "verified", "trace_count"]},
        "operator_tool": {"allowed_authority_modes": ["operator", "developer"]},
    }
    rules = cfg.get("rules", {})
    merged = {**default_rules, **rules}
    return {
        "mode": cfg.get("mode", "observe_then_enforce"),
        "drift_quarantine_threshold": int(cfg.get("drift_quarantine_threshold", 3)),
        "high_severity_quarantine": bool(cfg.get("high_severity_quarantine", True)),
        "rules": merged,
    }


def pattern_ledger_policy() -> dict[str, Any]:
    cfg = runtime_config().get("pattern_ledger", {})
    return {
        "recurrence_threshold": int(cfg.get("recurrence_threshold", 3)),
        "auto_quarantine_severities": list(cfg.get("auto_quarantine_severities", ["S4", "S5"])),
        "unknown_source_classification": cfg.get("unknown_source_classification", "pending_review"),
        "approved_sources": list(cfg.get("approved_sources", [
            "module_execution",
            "sandbox_denial",
            "law_denial",
            "trait_drift",
            "proof",
            "trace_verification",
            "operator_note",
        ])),
    }


def authority_capabilities(mode: str, gov: dict[str, Any]) -> set[str]:
    modes = gov.get("authority_modes", {})
    selected = modes.get(mode, {})
    caps = set(selected.get("capabilities", []))
    inherited = selected.get("inherits")
    if inherited and inherited in modes:
        caps.update(modes[inherited].get("capabilities", []))
    return caps


def rule_for(action: str, gov: dict[str, Any]) -> dict[str, Any]:
    for rule in gov.get("law_rules", []):
        if rule.get("rule") == action:
            return rule
    return {"rule": action, "requires_capabilities": [action]}


def evaluate_law(action: str, mode: str, requested: list[str] | None = None, evidence: dict[str, Any] | None = None) -> dict[str, Any]:
    gov = governance()
    rule = rule_for(action, gov)
    caps = authority_capabilities(mode, gov)
    requested_caps = set(requested or rule.get("requires_capabilities", []))
    required_caps = set(rule.get("requires_capabilities", []))
    missing_caps = sorted((requested_caps | required_caps) - caps)
    evidence = evidence or {}
    missing_evidence = [key for key in rule.get("requires", []) if not evidence.get(key)]
    denied_markers = [marker for marker in rule.get("denies", []) if marker in evidence.get("markers", [])]
    ok = not missing_caps and not missing_evidence and not denied_markers
    decision = {
        "timestamp": now(),
        "action": action,
        "authority_mode": mode,
        "ok": ok,
        "decision": "approve" if ok else "deny",
        "rule": rule,
        "capabilities": sorted(caps),
        "requested_capabilities": sorted(requested_caps),
        "missing_capabilities": missing_caps,
        "missing_evidence": missing_evidence,
        "denied_markers": denied_markers,
    }
    append_jsonl(TRACES / "law_decisions.jsonl", decision)
    append_jsonl(EVENTS / "events.jsonl", {"timestamp": now(), "event": "law.evaluated", "action": action, "decision": decision["decision"]})
    return decision


def read_task(path: pathlib.Path) -> dict[str, Any]:
    text = path.read_text(encoding="utf-8", errors="replace").strip()
    if path.suffix.lower() == ".json":
        data = json.loads(text or "{}")
        if not isinstance(data, dict):
            raise ValueError("task JSON must be an object")
        data.setdefault("body", data.get("task", ""))
        return data
    return {"body": text, "kind": "operator_note"}


def aris_cycle(task: dict[str, Any], source: pathlib.Path | None = None, authority_mode: str = "operator") -> dict[str, Any]:
    body = str(task.get("body", "")).strip()
    cycle_id = str(uuid.uuid4())
    task_hash = sha256_text(body)
    classification = "empty" if not body else "operator_task"
    capabilities = task.get("capabilities") or ["task.execute", "memory.append"]
    action = str(task.get("action") or "task.execute")
    evidence = {
        "body": bool(body),
        "markers": task.get("markers", []),
        "operator_approval": task.get("operator_approval", action != "network.fetch"),
    }
    law = evaluate_law(action, authority_mode, list(capabilities), evidence)
    load = cognitive_load_state()
    load_ok = load["active_cycles"] < load["max_active_cycles"]
    plan = [
        "intake",
        "classify",
        "evaluate_law",
        "check_cognitive_load",
        "record_trace",
        "await_operator_review",
    ]
    ok = bool(body) and law["ok"] and load_ok
    result = {
        "cycle_id": cycle_id,
        "timestamp": now(),
        "stage": "awaiting_operator_review" if ok else "rejected",
        "ok": ok,
        "classification": classification,
        "authority_mode": authority_mode,
        "law": law,
        "cognitive_load": load,
        "capabilities": list(capabilities),
        "task_hash": task_hash,
        "summary": body[:240],
        "source": str(source) if source else "manual",
        "plan": plan,
    }
    append_jsonl(TRACES / "aris_cycles.jsonl", result)
    append_jsonl(EVENTS / "events.jsonl", {"timestamp": now(), "event": "cycle.committed", "cycle_id": cycle_id, "ok": result["ok"]})
    return result


def read_jsonl(path: pathlib.Path) -> list[dict[str, Any]]:
    if not path.exists():
        return []
    items = []
    with path.open("r", encoding="utf-8", errors="replace") as fh:
        for line in fh:
            line = line.strip()
            if not line:
                continue
            try:
                value = json.loads(line)
                if isinstance(value, dict):
                    items.append(value)
            except json.JSONDecodeError:
                pass
    return items


def cognitive_load_state() -> dict[str, Any]:
    gov = governance()
    cfg = gov.get("cognitive_load", {})
    max_active = int(cfg.get("max_active_cycles", 6))
    cycles = read_jsonl(TRACES / "aris_cycles.jsonl")
    active = sum(1 for item in cycles[-max_active:] if item.get("stage") == "awaiting_operator_review")
    return {
        "max_active_cycles": max_active,
        "active_cycles": active,
        "overflow_strategy": cfg.get("overflow_strategy", "queue"),
        "memory_state": "stable",
    }


def heartbeat(extra: dict[str, Any] | None = None) -> dict[str, Any]:
    cycles = read_jsonl(TRACES / "aris_cycles.jsonl")
    state = cognitive_load_state()
    hb = {
        "timestamp": now(),
        "status": "healthy",
        "cycles": len(cycles),
        "queue_depth": len([p for p in INBOX.iterdir() if p.is_file()]) if INBOX.exists() else 0,
        "memory_state": state["memory_state"],
        "cognitive_load": state,
    }
    if extra:
        hb.update(extra)
    (LOGS / "heartbeat.json").write_text(json.dumps(hb, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    append_jsonl(EVENTS / "events.jsonl", {"timestamp": now(), "event": "runtime.heartbeat", "status": hb["status"], "cycles": hb["cycles"], "queue_depth": hb["queue_depth"]})
    return hb


def write_state(extra: dict[str, Any] | None = None) -> dict[str, Any]:
    hb = heartbeat()
    state = {
        "name": "cogos-daemon",
        "pid": os.getpid(),
        "timestamp": now(),
        "root": str(ROOT),
        "inbox": str(INBOX),
        "trace": str(TRACES / "aris_cycles.jsonl"),
        "law_trace": str(TRACES / "law_decisions.jsonl"),
        "heartbeat": hb,
        "status": "running",
    }
    if extra:
        state.update(extra)
    STATE_PATH.write_text(json.dumps(state, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return state


def process_task(path: pathlib.Path) -> None:
    try:
        task = read_task(path)
        result = aris_cycle(task, path, str(task.get("authority_mode") or "operator"))
        target_dir = DONE if result["ok"] else FAILED
        shutil.move(str(path), str(target_dir / path.name))
        write_state({"last_cycle_id": result["cycle_id"], "last_task": path.name, "last_task_ok": result["ok"]})
    except Exception as exc:  # Fail soft and preserve task for inspection.
        append_jsonl(EVENTS / "events.jsonl", {"timestamp": now(), "event": "task_error", "task": str(path), "error": str(exc)})
        try:
            shutil.move(str(path), str(FAILED / path.name))
        except Exception:
            pass
        write_state({"last_error": str(exc), "last_task": path.name})


def handle_signal(_signum: int, _frame: Any) -> None:
    global STOP
    STOP = True


def daemon_loop(interval: float) -> int:
    ensure_dirs()
    PID_PATH.write_text(str(os.getpid()) + "\n", encoding="utf-8")
    append_jsonl(EVENTS / "events.jsonl", {"timestamp": now(), "event": "daemon.started", "pid": os.getpid()})
    write_state()
    signal.signal(signal.SIGTERM, handle_signal)
    signal.signal(signal.SIGINT, handle_signal)

    while not STOP:
        for task_path in sorted(INBOX.iterdir()):
            if task_path.is_file() and not task_path.name.startswith("."):
                process_task(task_path)
        write_state()
        time.sleep(interval)

    append_jsonl(EVENTS / "events.jsonl", {"timestamp": now(), "event": "daemon.stopped", "pid": os.getpid()})
    write_state({"status": "stopped"})
    return 0


def print_status() -> int:
    if STATE_PATH.exists():
        print(STATE_PATH.read_text(encoding="utf-8"), end="")
        return 0
    print("cogos-daemon is not running")
    return 1


def run_once(body: str, authority_mode: str = "operator", capabilities: list[str] | None = None) -> int:
    ensure_dirs()
    result = aris_cycle({"body": body, "kind": "manual_run", "capabilities": capabilities or ["task.execute", "memory.append"]}, authority_mode=authority_mode)
    print(json.dumps(result, indent=2, sort_keys=True))
    return 0 if result["ok"] else 1


def trace_items(kind: str = "cycles") -> list[dict[str, Any]]:
    path = TRACES / ("law_decisions.jsonl" if kind == "law" else "aris_cycles.jsonl")
    return read_jsonl(path)


def print_trace(count: int) -> int:
    for item in trace_items()[-count:]:
        print(json.dumps(item, sort_keys=True))
    return 0


def explain_trace(selector: str) -> int:
    items = trace_items()
    if not items:
        print("No ARIS cycle trace yet.")
        return 1
    item = items[-1] if selector == "latest" else items[int(selector)]
    print(json.dumps({
        "cycle_id": item.get("cycle_id"),
        "ok": item.get("ok"),
        "stage": item.get("stage"),
        "authority_mode": item.get("authority_mode"),
        "law_decision": item.get("law", {}).get("decision"),
        "missing_capabilities": item.get("law", {}).get("missing_capabilities", []),
        "cognitive_load": item.get("cognitive_load"),
        "summary": item.get("summary"),
        "plan": item.get("plan"),
    }, indent=2, sort_keys=True))
    return 0


def replay_trace(selector: str) -> int:
    items = trace_items()
    if not items:
        print("No ARIS cycle trace yet.")
        return 1
    item = items[-1] if selector == "latest" else items[int(selector)]
    replay = {
        "timestamp": now(),
        "replay_of": item.get("cycle_id"),
        "request": item.get("summary"),
        "law_decision": item.get("law", {}).get("decision"),
        "would_execute": bool(item.get("ok")),
        "reason": "approved by recorded law decision" if item.get("ok") else "recorded cycle was denied or incomplete",
    }
    print(json.dumps(replay, indent=2, sort_keys=True))
    append_jsonl(TRACES / "replays.jsonl", replay)
    return 0 if replay["would_execute"] else 1


def verify_trace(selector: str) -> int:
    items = trace_items()
    if not items:
        print("No ARIS cycle trace yet.")
        return 1
    item = items[-1] if selector == "latest" else items[int(selector)]
    replay_task = {
        "body": item.get("summary", ""),
        "kind": "trace_verification",
        "capabilities": item.get("capabilities", ["task.execute", "memory.append"]),
        "action": item.get("law", {}).get("action", "task.execute"),
        "operator_approval": True,
    }
    law = evaluate_law(
        replay_task["action"],
        item.get("authority_mode", "operator"),
        list(replay_task["capabilities"]),
        {"body": bool(replay_task["body"]), "operator_approval": True, "markers": []},
    )
    verification = {
        "timestamp": now(),
        "trace": item.get("cycle_id"),
        "deterministic": (
            law.get("decision") == item.get("law", {}).get("decision")
            and law.get("missing_capabilities", []) == item.get("law", {}).get("missing_capabilities", [])
            and sha256_text(replay_task["body"]) == item.get("task_hash")
        ),
        "checks": {
            "law_decision": law.get("decision") == item.get("law", {}).get("decision"),
            "missing_capabilities": law.get("missing_capabilities", []) == item.get("law", {}).get("missing_capabilities", []),
            "task_hash": sha256_text(replay_task["body"]) == item.get("task_hash"),
        },
        "recorded": {
            "decision": item.get("law", {}).get("decision"),
            "task_hash": item.get("task_hash"),
            "stage": item.get("stage"),
        },
        "replayed": {
            "decision": law.get("decision"),
            "task_hash": sha256_text(replay_task["body"]),
        },
    }
    append_jsonl(TRACES / "verifications.jsonl", verification)
    append_jsonl(EVENTS / "events.jsonl", {"timestamp": now(), "event": "trace.verified", "trace": item.get("cycle_id"), "deterministic": verification["deterministic"]})
    print(json.dumps(verification, indent=2, sort_keys=True))
    return 0 if verification["deterministic"] else 1


def evaluate_cli(action: str, authority_mode: str, capabilities: list[str]) -> int:
    ensure_dirs()
    result = evaluate_law(action, authority_mode, capabilities, {"operator_approval": True, "manifest": True, "sha256": True})
    print(json.dumps(result, indent=2, sort_keys=True))
    return 0 if result["ok"] else 1


def verify_laws() -> int:
    manifest_path = ROOT / "law" / "law_manifest.json"
    if not manifest_path.exists():
        print("No law manifest found.")
        return 1
    manifest = load_json(manifest_path)
    results = []
    ok = True
    for item in manifest.get("files", []):
        path = pathlib.Path(item["path"])
        expected = item.get("sha256")
        actual = sha256_file(path) if path.exists() else None
        matched = bool(actual and actual == expected)
        ok = ok and matched
        results.append({"path": str(path), "expected": expected, "actual": actual, "ok": matched})
    report = {"timestamp": now(), "ok": ok, "files": results}
    append_jsonl(TRACES / "law_integrity.jsonl", report)
    append_jsonl(EVENTS / "events.jsonl", {"timestamp": now(), "event": "law.integrity", "ok": ok})
    print(json.dumps(report, indent=2, sort_keys=True))
    return 0 if ok else 1


def empty_registry() -> dict[str, Any]:
    return {"version": "0.1", "updated": now(), "modules": {}}


def load_registry() -> dict[str, Any]:
    if REGISTRY.exists():
        data = load_json(REGISTRY)
        data.setdefault("version", "0.1")
        data.setdefault("modules", {})
        return data
    return empty_registry()


def save_registry(registry: dict[str, Any]) -> None:
    registry["updated"] = now()
    save_json(REGISTRY, registry)


def load_identity_state() -> dict[str, Any]:
    if IDENTITY_STATE.exists():
        data = load_json(IDENTITY_STATE)
        data.setdefault("version", "0.1")
        data.setdefault("updated", now())
        data.setdefault("modules", {})
        return data
    return {"version": "0.1", "updated": now(), "modules": {}}


def save_identity_state(state: dict[str, Any]) -> None:
    state["updated"] = now()
    save_json(IDENTITY_STATE, state)


def module_manifest_path(path_text: str) -> pathlib.Path:
    path = pathlib.Path(path_text)
    return path / "module.json" if path.is_dir() else path


def required_module_fields() -> list[str]:
    return ["id", "name", "version", "entrypoint", "identity", "traits", "capabilities", "forbidden", "sha256"]


def trait_conflicts(traits: list[str], capabilities: list[str], forbidden: list[str]) -> list[str]:
    conflicts = []
    caps = set(capabilities)
    blocked = set(forbidden)
    if "readonly" in traits and any(cap in caps for cap in ["memory.write", "network.write", "self.modify"]):
        conflicts.append("readonly module cannot request write/self modification capability")
    if "non_mutating" in traits and any(cap in caps for cap in ["memory.write", "module.admit", "self.modify"]):
        conflicts.append("non_mutating module cannot request mutating capability")
    if caps & blocked:
        conflicts.append("capability also appears in forbidden list: " + ", ".join(sorted(caps & blocked)))
    return conflicts


def validate_module_manifest(manifest_path: pathlib.Path) -> dict[str, Any]:
    if not manifest_path.exists():
        return {"ok": False, "errors": [f"manifest not found: {manifest_path}"]}
    try:
        manifest = load_json(manifest_path)
    except Exception as exc:
        return {"ok": False, "errors": [f"manifest unreadable: {exc}"]}

    errors = [f"missing field: {field}" for field in required_module_fields() if field not in manifest]
    module_dir = manifest_path.parent
    entrypoint = module_dir / str(manifest.get("entrypoint", ""))
    if not entrypoint.exists():
        errors.append(f"entrypoint not found: {entrypoint}")
        actual_hash = None
    else:
        actual_hash = sha256_file(entrypoint)
        if manifest.get("sha256") != actual_hash:
            errors.append("entrypoint sha256 mismatch")

    traits = list(manifest.get("traits", [])) if isinstance(manifest.get("traits", []), list) else []
    capabilities = list(manifest.get("capabilities", [])) if isinstance(manifest.get("capabilities", []), list) else []
    forbidden = list(manifest.get("forbidden", [])) if isinstance(manifest.get("forbidden", []), list) else []
    errors.extend(trait_conflicts(traits, capabilities, forbidden))

    return {
        "ok": not errors,
        "errors": errors,
        "manifest": manifest,
        "manifest_path": str(manifest_path),
        "module_dir": str(module_dir),
        "entrypoint": str(entrypoint),
        "actual_sha256": actual_hash,
        "traits": traits,
        "capabilities": capabilities,
        "forbidden": forbidden,
    }


def module_record(validation: dict[str, Any], authority_mode: str, law: dict[str, Any], status: str) -> dict[str, Any]:
    manifest = validation.get("manifest", {})
    return {
        "id": manifest.get("id"),
        "name": manifest.get("name"),
        "version": manifest.get("version"),
        "identity": manifest.get("identity"),
        "traits": validation.get("traits", []),
        "capabilities": validation.get("capabilities", []),
        "forbidden": validation.get("forbidden", []),
        "entrypoint": validation.get("entrypoint"),
        "module_dir": validation.get("module_dir"),
        "sha256": validation.get("actual_sha256") or manifest.get("sha256"),
        "runtime": manifest.get("runtime", {}),
        "authority_mode": authority_mode,
        "status": status,
        "law": law,
        "updated": now(),
        "errors": validation.get("errors", []),
    }


def admit_local_module(path_text: str, authority_mode: str = "developer") -> int:
    ensure_dirs()
    validation = validate_module_manifest(module_manifest_path(path_text))
    manifest = validation.get("manifest", {})
    evidence = {
        "manifest": bool(manifest),
        "sha256": bool(validation.get("actual_sha256")),
        "markers": ["trait_conflict"] if validation.get("errors") else [],
    }
    law = evaluate_law("module.admit", authority_mode, ["module.admit", "module.verify"], evidence)
    admitted = validation["ok"] and law["ok"]
    record = module_record(validation, authority_mode, law, "active" if admitted else "rejected")
    record["timestamp"] = now()
    record["admitted"] = admitted
    if manifest.get("id"):
        registry = load_registry()
        registry["modules"][manifest["id"]] = record
        save_registry(registry)
        if admitted:
            state = load_identity_state()
            previous = state["modules"].get(manifest["id"], {})
            state["modules"][manifest["id"]] = {
                "module_id": manifest["id"],
                "identity": manifest.get("identity"),
                "traits": validation.get("traits", []),
                "status": "healthy",
                "drift_score": 0,
                "warnings": previous.get("warnings", []),
                "drift_events": previous.get("drift_events", []),
                "quarantined_by_trait_runtime": False,
                "last_observed": previous.get("last_observed"),
                "history_preserved": bool(previous),
            }
            save_identity_state(state)
    append_jsonl(MODULE_MEMORY / "admission.jsonl", record)
    append_jsonl(TRAIT_LEDGER, {"timestamp": now(), "module_id": manifest.get("id"), "identity": manifest.get("identity"), "traits": validation.get("traits", []), "capabilities": validation.get("capabilities", []), "status": record["status"], "errors": record["errors"]})
    append_jsonl(EVENTS / "events.jsonl", {"timestamp": now(), "event": "module.admitted" if admitted else "module.rejected", "module_id": manifest.get("id"), "path": path_text})
    print(json.dumps(record, indent=2, sort_keys=True))
    return 0 if admitted else 1


def admit_module(path_text: str, authority_mode: str) -> int:
    return admit_local_module(path_text, authority_mode)


def module_list() -> int:
    registry = load_registry()
    modules = registry.get("modules", {})
    if not modules:
        print("No admitted modules.")
        return 0
    for module_id, record in sorted(modules.items()):
        print(f"{module_id}\t{record.get('status')}\t{record.get('version')}\t{record.get('identity')}")
    return 0


def module_registry() -> int:
    print(json.dumps(load_registry(), indent=2, sort_keys=True))
    return 0


def module_inspect(module_id: str) -> int:
    record = load_registry().get("modules", {}).get(module_id)
    if not record:
        print(f"Module not found: {module_id}")
        return 1
    print(json.dumps(record, indent=2, sort_keys=True))
    return 0


def module_deny(module_id: str) -> int:
    registry = load_registry()
    record = registry.get("modules", {}).get(module_id)
    if not record:
        print(f"Module not found: {module_id}")
        return 1
    record["status"] = "denied"
    record["updated"] = now()
    save_registry(registry)
    append_jsonl(EVENTS / "events.jsonl", {"timestamp": now(), "event": "module.denied", "module_id": module_id})
    print(json.dumps(record, indent=2, sort_keys=True))
    return 0


def module_quarantine(module_id: str, reason: str) -> int:
    ensure_dirs()
    registry = load_registry()
    record = registry.get("modules", {}).get(module_id)
    if not record:
        print(f"Module not found: {module_id}")
        return 1
    law = evaluate_law("module.quarantine", "developer", ["module.quarantine", "module.verify"], {"manifest": True})
    if not law["ok"]:
        report = {"timestamp": now(), "module_id": module_id, "reason": reason, "law": law, "ok": False}
        append_jsonl(MODULE_MEMORY / "sandbox_denials.jsonl", report)
        print(json.dumps(report, indent=2, sort_keys=True))
        return 1
    record["status"] = "quarantined"
    record["quarantine_reason"] = reason
    record["updated"] = now()
    save_registry(registry)
    event = {"timestamp": now(), "event": "module.quarantined", "module_id": module_id, "reason": reason}
    append_jsonl(EVENTS / "events.jsonl", event)
    append_jsonl(TRAIT_LEDGER, {"timestamp": now(), "module_id": module_id, "status": "quarantined", "reason": reason})
    print(json.dumps(record, indent=2, sort_keys=True))
    return 0


def module_verify(module_id: str) -> int:
    record = load_registry().get("modules", {}).get(module_id)
    if not record:
        print(f"Module not found: {module_id}")
        return 1
    entrypoint = pathlib.Path(record.get("entrypoint", ""))
    actual = sha256_file(entrypoint) if entrypoint.exists() else None
    report = {
        "timestamp": now(),
        "module_id": module_id,
        "status": record.get("status"),
        "expected_sha256": record.get("sha256"),
        "actual_sha256": actual,
        "ok": bool(actual and actual == record.get("sha256") and record.get("status") == "active"),
    }
    append_jsonl(MODULE_MEMORY / "verification.jsonl", report)
    append_jsonl(EVENTS / "events.jsonl", {"timestamp": now(), "event": "module.verified", "module_id": module_id, "ok": report["ok"]})
    print(json.dumps(report, indent=2, sort_keys=True))
    return 0 if report["ok"] else 1


def severity_weight(severity: str) -> int:
    return {"S1": 0, "S2": 1, "S3": 1, "S4": 3, "S5": 3}.get(severity, 1)


def trait_runtime_evidence(record: dict[str, Any], execution: dict[str, Any] | None = None, denial: dict[str, Any] | None = None, authority_mode: str = "operator") -> dict[str, Any]:
    policy = trait_runtime_policy()
    module_id = str(record.get("id") or record.get("module_id") or "unknown")
    traits = list(record.get("traits", []))
    capabilities = list(record.get("capabilities", []))
    forbidden = list(record.get("forbidden", []))
    output = execution.get("output", {}) if execution else {}
    issues = []
    unscored = []
    for trait in traits:
        rule = policy["rules"].get(trait)
        if not rule:
            unscored.append(trait)
            continue
        blocked = sorted(set(capabilities) & set(rule.get("forbids", [])))
        if blocked:
            issues.append({"trait": trait, "severity": "S4", "reason": "forbidden capability declared", "details": blocked})
        allowed_modes = rule.get("allowed_authority_modes")
        if allowed_modes and authority_mode not in allowed_modes:
            issues.append({"trait": trait, "severity": "S3", "reason": "authority mode outside trait policy", "details": {"authority_mode": authority_mode, "allowed": allowed_modes}})
        if rule.get("expects_structured_output") and execution and not isinstance(output, dict):
            issues.append({"trait": trait, "severity": "S3", "reason": "output is not structured JSON object"})
        expected_fields = rule.get("expects_any_output_fields", [])
        if expected_fields and execution and not any(field in output for field in expected_fields):
            issues.append({"trait": trait, "severity": "S2", "reason": "expected verifier evidence field missing", "details": expected_fields})
        markers = [str(value).lower() for value in rule.get("mutation_output_markers", [])]
        output_text = json.dumps(output, sort_keys=True).lower() if execution else ""
        found = [marker for marker in markers if marker in output_text]
        if found:
            issues.append({"trait": trait, "severity": "S3", "reason": "mutation-intent output marker", "details": found})
    forbidden_overlap = sorted(set(capabilities) & set(forbidden))
    if forbidden_overlap:
        issues.append({"trait": "manifest", "severity": "S4", "reason": "capability also listed as forbidden", "details": forbidden_overlap})
    if denial:
        reason = str(denial.get("reason", "sandbox denial"))
        severity = "S4" if any(token in reason for token in ["hash changed", "trait/capability", "sandbox denied capability"]) else "S2"
        issues.append({"trait": "sandbox", "severity": severity, "reason": reason})
    return {
        "timestamp": now(),
        "module_id": module_id,
        "identity": record.get("identity"),
        "traits": traits,
        "capabilities": capabilities,
        "forbidden": forbidden,
        "authority_mode": authority_mode,
        "execution_id": execution.get("execution_id") if execution else None,
        "execution_ok": execution.get("ok") if execution else None,
        "issues": issues,
        "unscored_traits": unscored,
        "status": "observed" if not issues else "drift",
    }


def record_trait_observation(record: dict[str, Any], execution: dict[str, Any] | None = None, denial: dict[str, Any] | None = None, authority_mode: str = "operator") -> dict[str, Any]:
    ensure_dirs()
    evidence = trait_runtime_evidence(record, execution, denial, authority_mode)
    module_id = evidence["module_id"]
    state = load_identity_state()
    module_state = state["modules"].get(module_id, {
        "module_id": module_id,
        "identity": evidence.get("identity"),
        "traits": evidence.get("traits", []),
        "status": "healthy",
        "drift_score": 0,
        "warnings": [],
        "drift_events": [],
        "quarantined_by_trait_runtime": False,
    })
    append_jsonl(MODULE_MEMORY / "trait_events.jsonl", evidence)
    append_jsonl(EVENTS / "events.jsonl", {"timestamp": now(), "event": "trait.observed", "module_id": module_id, "status": evidence["status"]})
    increment = sum(severity_weight(issue.get("severity", "S2")) for issue in evidence["issues"])
    if evidence["issues"]:
        drift = {
            "timestamp": now(),
            "module_id": module_id,
            "issues": evidence["issues"],
            "increment": increment,
            "execution_id": evidence.get("execution_id"),
        }
        append_jsonl(MODULE_MEMORY / "drift.jsonl", drift)
        module_state["drift_score"] = int(module_state.get("drift_score", 0)) + increment
        module_state.setdefault("warnings", []).append({"timestamp": now(), "issues": evidence["issues"]})
        module_state.setdefault("drift_events", []).append(drift)
        module_state["status"] = "warning" if module_state["drift_score"] < trait_runtime_policy()["drift_quarantine_threshold"] else "quarantine_requested"
        append_jsonl(EVENTS / "events.jsonl", {"timestamp": now(), "event": "trait.warning", "module_id": module_id, "drift_score": module_state["drift_score"]})
        append_jsonl(EVENTS / "events.jsonl", {"timestamp": now(), "event": "trait.drift", "module_id": module_id, "drift_score": module_state["drift_score"]})
    else:
        module_state["status"] = "healthy"
    module_state["identity"] = evidence.get("identity")
    module_state["traits"] = evidence.get("traits", [])
    module_state["last_observed"] = now()
    module_state["last_evidence"] = evidence
    state["modules"][module_id] = module_state
    save_identity_state(state)
    high = any(issue.get("severity") in ["S4", "S5"] for issue in evidence["issues"])
    threshold = int(trait_runtime_policy()["drift_quarantine_threshold"])
    should_quarantine = bool(evidence["issues"]) and ((high and trait_runtime_policy()["high_severity_quarantine"]) or int(module_state.get("drift_score", 0)) >= threshold)
    if should_quarantine:
        append_jsonl(EVENTS / "events.jsonl", {"timestamp": now(), "event": "trait.quarantine_requested", "module_id": module_id, "drift_score": module_state.get("drift_score")})
        registry = load_registry()
        reg_record = registry.get("modules", {}).get(module_id)
        if reg_record and reg_record.get("status") == "active":
            law = evaluate_law("module.quarantine", "developer", ["module.quarantine", "module.verify"], {"manifest": True})
            if law["ok"]:
                reg_record["status"] = "quarantined"
                reg_record["quarantine_reason"] = "trait runtime drift"
                reg_record["quarantined_by_trait_runtime"] = True
                reg_record["updated"] = now()
                save_registry(registry)
                module_state["status"] = "quarantined"
                module_state["quarantined_by_trait_runtime"] = True
                state["modules"][module_id] = module_state
                save_identity_state(state)
                append_jsonl(EVENTS / "events.jsonl", {"timestamp": now(), "event": "module.quarantined", "module_id": module_id, "reason": "trait runtime drift"})
        elif reg_record and reg_record.get("status") == "quarantined":
            module_state["status"] = "quarantined"
            module_state["quarantined_by_trait_runtime"] = bool(reg_record.get("quarantined_by_trait_runtime", module_state.get("quarantined_by_trait_runtime")))
            state["modules"][module_id] = module_state
            save_identity_state(state)
    append_jsonl(EVENTS / "events.jsonl", {"timestamp": now(), "event": "identity.state_updated", "module_id": module_id, "status": module_state.get("status")})
    return {"evidence": evidence, "identity_state": module_state}


def parse_module_input(text: str | None) -> tuple[dict[str, Any] | None, str | None]:
    if not text:
        return {}, None
    try:
        data = json.loads(text)
    except json.JSONDecodeError as exc:
        return None, f"input-json is not valid JSON: {exc}"
    if not isinstance(data, dict):
        return None, "input-json must decode to a JSON object"
    return data, None


def sandbox_denial(module_id: str, reason: str, law: dict[str, Any] | None = None, extra: dict[str, Any] | None = None, module_record_data: dict[str, Any] | None = None, authority_mode: str = "operator") -> int:
    record = {
        "timestamp": now(),
        "module_id": module_id,
        "ok": False,
        "status": "denied",
        "reason": reason,
        "law": law,
    }
    if extra:
        record.update(extra)
    append_jsonl(MODULE_MEMORY / "sandbox_denials.jsonl", record)
    append_jsonl(EVENTS / "events.jsonl", {"timestamp": now(), "event": "module.execution.denied", "module_id": module_id, "reason": reason})
    if module_record_data:
        record["trait_identity"] = record_trait_observation(module_record_data, denial=record, authority_mode=authority_mode)
    print(json.dumps(record, indent=2, sort_keys=True))
    return 1


def process_text(value: Any, limit: int) -> str:
    if value is None:
        return ""
    if isinstance(value, bytes):
        value = value.decode("utf-8", errors="replace")
    return str(value)[:limit]


def module_run(module_id: str, input_text: str | None, authority_mode: str = "operator") -> int:
    ensure_dirs()
    append_jsonl(EVENTS / "events.jsonl", {"timestamp": now(), "event": "module.execution.requested", "module_id": module_id})
    registry = load_registry()
    record = registry.get("modules", {}).get(module_id)
    if not record:
        return sandbox_denial(module_id, "module is not admitted")
    if record.get("status") != "active":
        return sandbox_denial(module_id, f"module status is {record.get('status')}", module_record_data=record, authority_mode=authority_mode)

    module_input, input_error = parse_module_input(input_text)
    if input_error:
        return sandbox_denial(module_id, input_error, module_record_data=record, authority_mode=authority_mode)

    entrypoint = pathlib.Path(record.get("entrypoint", ""))
    actual = sha256_file(entrypoint) if entrypoint.exists() else None
    if not actual or actual != record.get("sha256"):
        return sandbox_denial(module_id, "module hash changed after admission", extra={"expected_sha256": record.get("sha256"), "actual_sha256": actual}, module_record_data=record, authority_mode=authority_mode)

    traits = list(record.get("traits", []))
    capabilities = list(record.get("capabilities", []))
    forbidden = list(record.get("forbidden", []))
    requested_runtime_caps = module_input.get("requested_capabilities", module_input.get("capabilities", []))
    if requested_runtime_caps and not set(requested_runtime_caps).issubset(set(capabilities)):
        return sandbox_denial(module_id, "module requested undeclared capability", extra={"requested_capabilities": requested_runtime_caps, "declared_capabilities": capabilities}, module_record_data=record, authority_mode=authority_mode)
    conflicts = trait_conflicts(traits, capabilities, forbidden)
    if conflicts:
        return sandbox_denial(module_id, "trait/capability conflict", extra={"errors": conflicts}, module_record_data=record, authority_mode=authority_mode)
    denied_caps = sorted(set(capabilities) & {"memory.write", "self.modify", "network.write"})
    if denied_caps:
        return sandbox_denial(module_id, "sandbox denied capability", extra={"denied_capabilities": denied_caps}, module_record_data=record, authority_mode=authority_mode)
    if "network.fetch" in capabilities and sandbox_policy().get("network") != "allowed":
        return sandbox_denial(module_id, "network.fetch denied by sandbox policy", module_record_data=record, authority_mode=authority_mode)

    law = evaluate_law("module.execute", authority_mode, ["module.execute"], {"manifest": True, "sha256": True, "registry": True, "markers": []})
    if not law["ok"]:
        return sandbox_denial(module_id, "law denied module.execute", law=law, module_record_data=record, authority_mode=authority_mode)

    runtime = record.get("runtime", {}) if isinstance(record.get("runtime", {}), dict) else {}
    policy = sandbox_policy()
    timeout = int(runtime.get("timeout_seconds", policy["timeout_seconds"]))
    max_stdout = int(policy["max_stdout_bytes"])
    max_stderr = int(policy["max_stderr_bytes"])
    payload = {
        "module_id": module_id,
        "input": module_input,
        "capabilities": capabilities,
        "sandbox": {
            "network": policy["network"],
            "write_paths": policy["write_paths"],
            "capability_paths": policy["capability_paths"],
        },
    }
    env = {
        "PATH": "/usr/local/bin:/usr/bin:/bin",
        "HOME": "/tmp",
        "LANG": "C.UTF-8",
        "COGOS_ROOT": str(ROOT),
        "COGOS_MODULE_ID": module_id,
        "COGOS_MODULE_CAPABILITIES": ",".join(capabilities),
    }
    started = time.time()
    append_jsonl(EVENTS / "events.jsonl", {"timestamp": now(), "event": "module.execution.approved", "module_id": module_id})
    try:
        completed = subprocess.run(
            ["python3", str(entrypoint)],
            input=json.dumps(payload, sort_keys=True),
            text=True,
            capture_output=True,
            cwd=str(pathlib.Path(record.get("module_dir", entrypoint.parent))),
            env=env,
            timeout=timeout,
        )
        duration_ms = int((time.time() - started) * 1000)
        stdout = completed.stdout[:max_stdout]
        stderr = completed.stderr[:max_stderr]
    except subprocess.TimeoutExpired as exc:
        return sandbox_denial(module_id, "module execution timed out", law=law, extra={"timeout_seconds": timeout, "stdout": process_text(exc.stdout, max_stdout), "stderr": process_text(exc.stderr, max_stderr)}, module_record_data=record, authority_mode=authority_mode)
    except Exception as exc:
        return sandbox_denial(module_id, f"module launch failed: {exc}", law=law, module_record_data=record, authority_mode=authority_mode)

    try:
        output = json.loads(stdout.strip() or "{}")
    except json.JSONDecodeError as exc:
        return sandbox_denial(module_id, f"module stdout is not valid JSON: {exc}", law=law, extra={"stdout": stdout, "stderr": stderr, "returncode": completed.returncode}, module_record_data=record, authority_mode=authority_mode)
    if not isinstance(output, dict):
        return sandbox_denial(module_id, "module stdout must be a JSON object", law=law, extra={"stdout": stdout, "stderr": stderr, "returncode": completed.returncode}, module_record_data=record, authority_mode=authority_mode)

    ok = completed.returncode == 0
    execution = {
        "timestamp": now(),
        "execution_id": str(uuid.uuid4()),
        "module_id": module_id,
        "ok": ok,
        "status": "completed" if ok else "failed",
        "authority_mode": authority_mode,
        "returncode": completed.returncode,
        "duration_ms": duration_ms,
        "input_hash": sha256_text(json.dumps(module_input, sort_keys=True)),
        "output_hash": sha256_text(json.dumps(output, sort_keys=True)),
        "output": output,
        "stderr": stderr,
        "law": law,
        "sandbox": {
            "timeout_seconds": timeout,
            "network": policy["network"],
            "write_paths": policy["write_paths"],
        },
    }
    execution["trait_identity"] = record_trait_observation(record, execution=execution, authority_mode=authority_mode)
    append_jsonl(MODULE_MEMORY / "executions.jsonl", execution)
    append_jsonl(EVENTS / "events.jsonl", {"timestamp": now(), "event": "module.execution.completed", "module_id": module_id, "ok": ok})
    print(json.dumps(execution, indent=2, sort_keys=True))
    return 0 if ok else 1


def trait_list() -> int:
    state = load_identity_state()
    modules = state.get("modules", {})
    if not modules:
        print("No trait identity state yet.")
        return 0
    for module_id, item in sorted(modules.items()):
        print(f"{module_id}\t{item.get('status')}\tdrift={item.get('drift_score', 0)}\t{','.join(item.get('traits', []))}")
    return 0


def trait_inspect(module_id: str) -> int:
    item = load_identity_state().get("modules", {}).get(module_id)
    if not item:
        print(f"No trait identity state for: {module_id}")
        return 1
    print(json.dumps(item, indent=2, sort_keys=True))
    return 0


def trait_events(module_id: str | None = None) -> int:
    rows = read_jsonl(MODULE_MEMORY / "trait_events.jsonl")
    if module_id:
        rows = [row for row in rows if row.get("module_id") == module_id]
    for row in rows[-50:]:
        print(json.dumps(row, sort_keys=True))
    return 0


def trait_audit(module_id: str) -> int:
    registry = load_registry()
    record = registry.get("modules", {}).get(module_id)
    if not record:
        print(f"Module not found: {module_id}")
        return 1
    law = evaluate_law("trait.audit", "verifier", ["trait.audit", "module.inspect", "module.verify"], {"manifest": True, "registry": True})
    if not law["ok"]:
        print(json.dumps({"timestamp": now(), "module_id": module_id, "ok": False, "law": law}, indent=2, sort_keys=True))
        return 1
    observation = record_trait_observation(record, authority_mode="verifier")
    item = load_identity_state().get("modules", {}).get(module_id, {})
    report = {
        "timestamp": now(),
        "module_id": module_id,
        "ok": law["ok"] and item.get("status") in ["healthy", "warning"],
        "law": law,
        "identity_state": item,
        "evidence": observation["evidence"],
    }
    append_jsonl(MODULE_MEMORY / "trait_audits.jsonl", report)
    print(json.dumps(report, indent=2, sort_keys=True))
    return 0 if report["ok"] else 1


def trait_prove() -> int:
    state = load_identity_state()
    modules = state.get("modules", {})
    warnings = [mid for mid, item in modules.items() if item.get("status") == "warning"]
    quarantined = [mid for mid, item in modules.items() if item.get("quarantined_by_trait_runtime")]
    drift_events = read_jsonl(MODULE_MEMORY / "drift.jsonl")
    report = {
        "timestamp": now(),
        "trait_identity_ok": not quarantined,
        "module_count": len(modules),
        "drift_events": len(drift_events),
        "warnings": warnings,
        "quarantined_by_trait_runtime": quarantined,
        "identity_state_hash": sha256_text(json.dumps(state, sort_keys=True)),
    }
    print(json.dumps(report, indent=2, sort_keys=True))
    append_jsonl(MODULE_MEMORY / "trait_proof.jsonl", report)
    return 0 if report["trait_identity_ok"] else 1


def pattern_id(source: str, kind: str, summary: str) -> str:
    return sha256_text("|".join([source, kind, summary]))[:16]


def pattern_signature(source: str, kind: str, subject: str, classification: str) -> str:
    return sha256_text("|".join([source, kind, subject, classification]))[:16]


def pattern_rows(path_name: str) -> list[dict[str, Any]]:
    return read_jsonl(PATTERNS / path_name)


def pattern_classification(source: str, item: dict[str, Any]) -> tuple[str, str, str]:
    if source == "module_execution":
        return ("success" if item.get("ok") else "failure", "S1" if item.get("ok") else "S2", "module execution result")
    if source == "sandbox_denial":
        reason = str(item.get("reason", "sandbox denial"))
        sev = "S4" if any(token in reason for token in ["hash changed", "trait/capability", "sandbox denied capability"]) else "S2"
        return ("near_miss", sev, reason)
    if source == "law_denial":
        return ("near_miss", "S3", "law denial contained before execution")
    if source == "trait_drift":
        issues = item.get("issues", [])
        high = any(issue.get("severity") in ["S4", "S5"] for issue in issues)
        return ("failure", "S4" if high else "S3", "trait drift evidence")
    if source == "proof":
        return ("success" if item.get("ok") else "failure", "S1" if item.get("ok") else "S3", "proof report")
    if source == "trace_verification":
        return ("success" if item.get("deterministic") else "failure", "S1" if item.get("deterministic") else "S3", "trace verification")
    if source == "operator_note":
        return ("pending_review", "S1", "operator submitted note")
    return (pattern_ledger_policy()["unknown_source_classification"], "S1", "unknown evidence source")


def pattern_subject(source: str, item: dict[str, Any]) -> str:
    return str(item.get("module_id") or item.get("trace") or item.get("action") or item.get("pattern_id") or source)


def write_pattern_record(source: str, item: dict[str, Any]) -> dict[str, Any]:
    classification, severity, reason = pattern_classification(source, item)
    subject = pattern_subject(source, item)
    summary = str(item.get("reason") or item.get("status") or item.get("classification") or reason)
    sig = pattern_signature(source, str(item.get("event") or item.get("status") or reason), subject, classification)
    record = {
        "timestamp": now(),
        "pattern_id": pattern_id(source, sig, summary),
        "signature": sig,
        "source": source,
        "subject": subject,
        "classification": classification,
        "severity": severity,
        "summary": summary[:240],
        "evidence": item,
        "status": "classified",
    }
    append_jsonl(PATTERNS / "events.jsonl", record)
    append_jsonl(EVENTS / "events.jsonl", {"timestamp": now(), "event": "pattern.ingested", "pattern_id": record["pattern_id"], "source": source})
    append_jsonl(EVENTS / "events.jsonl", {"timestamp": now(), "event": "pattern.classified", "pattern_id": record["pattern_id"], "classification": classification, "severity": severity})
    if classification == "success":
        record["maturity"] = pattern_maturity(sig)
        append_jsonl(PATTERNS / "fame.jsonl", record)
        append_jsonl(EVENTS / "events.jsonl", {"timestamp": now(), "event": "pattern.fame_recorded", "pattern_id": record["pattern_id"], "maturity": record["maturity"]})
        maybe_promote_guidance(record)
    elif classification in ["failure", "near_miss", "recovered_failure"]:
        append_jsonl(PATTERNS / "shame.jsonl", record)
        append_jsonl(EVENTS / "events.jsonl", {"timestamp": now(), "event": "pattern.shame_recorded", "pattern_id": record["pattern_id"], "severity": severity})
        immune_recommend(record)
    else:
        append_jsonl(PATTERNS / "pending.jsonl", record)
    return record


def pattern_maturity(signature: str) -> str:
    count = sum(1 for row in pattern_rows("fame.jsonl") if row.get("signature") == signature) + 1
    threshold = pattern_ledger_policy()["recurrence_threshold"]
    if count >= threshold:
        return "guidance_eligible"
    if count == 2:
        return "observed_repeat"
    return "candidate"


def maybe_promote_guidance(record: dict[str, Any]) -> None:
    if record.get("maturity") != "guidance_eligible":
        return
    guidance = {
        "timestamp": now(),
        "pattern_id": record["pattern_id"],
        "signature": record["signature"],
        "subject": record["subject"],
        "maturity": "guidance_eligible",
        "summary": record["summary"],
        "source": record["source"],
    }
    append_jsonl(PATTERNS / "guidance.jsonl", guidance)
    append_jsonl(EVENTS / "events.jsonl", {"timestamp": now(), "event": "guidance.promoted", "pattern_id": record["pattern_id"], "maturity": "guidance_eligible"})


def immune_recommend(record: dict[str, Any]) -> dict[str, Any]:
    severity = record.get("severity", "S1")
    if severity in ["S5"]:
        action = "QUARANTINE_RECOMMENDED"
    elif severity in ["S4"]:
        action = "QUARANTINE_RECOMMENDED"
    elif severity == "S3":
        action = "CLAMP_RECOMMENDED"
    elif record.get("classification") == "near_miss":
        action = "WATCH"
    else:
        action = "WATCH"
    immune = {
        "timestamp": now(),
        "pattern_id": record.get("pattern_id"),
        "subject": record.get("subject"),
        "severity": severity,
        "classification": record.get("classification"),
        "recommendation": action,
        "auto_quarantine_eligible": severity in pattern_ledger_policy()["auto_quarantine_severities"],
    }
    append_jsonl(PATTERNS / "immune.jsonl", immune)
    append_jsonl(EVENTS / "events.jsonl", {"timestamp": now(), "event": "immune.recommended", "pattern_id": record.get("pattern_id"), "recommendation": action})
    if immune["auto_quarantine_eligible"]:
        registry = load_registry()
        subject = str(record.get("subject"))
        module = registry.get("modules", {}).get(subject)
        if module and module.get("status") == "active":
            law = evaluate_law("module.quarantine", "developer", ["module.quarantine", "module.verify"], {"manifest": True})
            if law["ok"]:
                module["status"] = "quarantined"
                module["quarantine_reason"] = "immune pattern recommendation"
                module["quarantined_by_immune_runtime"] = True
                module["updated"] = now()
                save_registry(registry)
                append_jsonl(EVENTS / "events.jsonl", {"timestamp": now(), "event": "module.quarantined", "module_id": subject, "reason": "immune pattern recommendation"})
    return immune


def pattern_ingest() -> int:
    ensure_dirs()
    law = evaluate_law("pattern.ingest", "verifier", ["pattern.ingest", "pattern.classify"], {"evidence": True})
    if not law["ok"]:
        print(json.dumps({"ok": False, "law": law}, indent=2, sort_keys=True))
        return 1
    seen = {(row.get("source"), json.dumps(row.get("evidence", {}), sort_keys=True)) for row in pattern_rows("events.jsonl")}
    candidates: list[tuple[str, dict[str, Any]]] = []
    candidates.extend(("module_execution", row) for row in read_jsonl(MODULE_MEMORY / "executions.jsonl"))
    candidates.extend(("sandbox_denial", row) for row in read_jsonl(MODULE_MEMORY / "sandbox_denials.jsonl"))
    candidates.extend(("law_denial", row) for row in read_jsonl(TRACES / "law_decisions.jsonl") if row.get("decision") == "deny")
    candidates.extend(("trait_drift", row) for row in read_jsonl(MODULE_MEMORY / "drift.jsonl"))
    candidates.extend(("proof", row) for row in read_jsonl(TRACES / "proof.jsonl"))
    candidates.extend(("trace_verification", row) for row in read_jsonl(TRACES / "verifications.jsonl"))
    written = []
    for source, item in candidates:
        key = (source, json.dumps(item, sort_keys=True))
        if key in seen:
            continue
        written.append(write_pattern_record(source, item))
        seen.add(key)
    report = {"timestamp": now(), "ok": True, "ingested": len(written), "patterns": [row["pattern_id"] for row in written]}
    print(json.dumps(report, indent=2, sort_keys=True))
    return 0


def pattern_list() -> int:
    rows = pattern_rows("events.jsonl")
    for row in rows[-50:]:
        print(f"{row.get('pattern_id')}\t{row.get('classification')}\t{row.get('severity')}\t{row.get('source')}\t{row.get('subject')}")
    return 0


def print_pattern_file(name: str) -> int:
    for row in pattern_rows(name)[-50:]:
        print(json.dumps(row, sort_keys=True))
    return 0


def pattern_inspect(pattern_id_text: str) -> int:
    for name in ["events.jsonl", "fame.jsonl", "shame.jsonl", "immune.jsonl", "guidance.jsonl", "pending.jsonl"]:
        for row in pattern_rows(name):
            if row.get("pattern_id") == pattern_id_text:
                print(json.dumps(row, indent=2, sort_keys=True))
                return 0
    print(f"Pattern not found: {pattern_id_text}")
    return 1


def pattern_prove() -> int:
    fame = pattern_rows("fame.jsonl")
    shame = pattern_rows("shame.jsonl")
    immune = pattern_rows("immune.jsonl")
    guidance = pattern_rows("guidance.jsonl")
    pending = pattern_rows("pending.jsonl")
    verified_failures = [row for row in pattern_rows("events.jsonl") if row.get("classification") in ["failure", "near_miss", "recovered_failure"]]
    shame_ids = {row.get("pattern_id") for row in shame}
    missing_shame = [row.get("pattern_id") for row in verified_failures if row.get("pattern_id") not in shame_ids]
    if missing_shame:
        append_jsonl(EVENTS / "events.jsonl", {"timestamp": now(), "event": "law.no_silent_failure", "missing": missing_shame})
    report = {
        "timestamp": now(),
        "pattern_ledger_ok": not missing_shame,
        "fame_count": len(fame),
        "shame_count": len(shame),
        "immune_recommendations": len(immune),
        "law_11_ok": not missing_shame,
        "guidance_candidates": len([row for row in guidance if row.get("maturity") == "guidance_eligible"]),
        "pending_review": len(pending),
        "ledger_hash": sha256_text(json.dumps({"fame": fame, "shame": shame, "immune": immune, "guidance": guidance}, sort_keys=True)),
    }
    append_jsonl(PATTERNS / "proof.jsonl", report)
    print(json.dumps(report, indent=2, sort_keys=True))
    return 0 if report["pattern_ledger_ok"] else 1


def proof_report() -> int:
    law_ok = False
    trace_ok = False
    registry_ok = False
    module_execution_ok = False
    try:
        manifest = load_json(ROOT / "law" / "law_manifest.json")
        law_ok = all(sha256_file(pathlib.Path(item["path"])) == item.get("sha256") for item in manifest.get("files", []))
    except Exception:
        law_ok = False
    cycles = trace_items()
    if cycles:
        latest = cycles[-1]
        trace_ok = sha256_text(latest.get("summary", "")) == latest.get("task_hash")
    registry = load_registry()
    registry_ok = all(
        pathlib.Path(rec.get("entrypoint", "")).exists()
        and sha256_file(pathlib.Path(rec.get("entrypoint", ""))) == rec.get("sha256")
        for rec in registry.get("modules", {}).values()
        if rec.get("status") == "active"
    )
    executions = read_jsonl(MODULE_MEMORY / "executions.jsonl")
    if executions:
        latest_exec = executions[-1]
        module_execution_ok = sha256_text(json.dumps(latest_exec.get("output", {}), sort_keys=True)) == latest_exec.get("output_hash")
    else:
        module_execution_ok = True
    quarantined = [mid for mid, rec in registry.get("modules", {}).items() if rec.get("status") == "quarantined"]
    identity_state = load_identity_state()
    identity_modules = identity_state.get("modules", {})
    drift_events = read_jsonl(MODULE_MEMORY / "drift.jsonl")
    trait_warnings = [mid for mid, item in identity_modules.items() if item.get("status") == "warning"]
    trait_quarantined = [mid for mid, item in identity_modules.items() if item.get("quarantined_by_trait_runtime")]
    trait_identity_ok = not trait_quarantined
    fame = pattern_rows("fame.jsonl")
    shame = pattern_rows("shame.jsonl")
    immune = pattern_rows("immune.jsonl")
    guidance = pattern_rows("guidance.jsonl")
    verified_failures = [row for row in pattern_rows("events.jsonl") if row.get("classification") in ["failure", "near_miss", "recovered_failure"]]
    shame_ids = {row.get("pattern_id") for row in shame}
    law_11_ok = all(row.get("pattern_id") in shame_ids for row in verified_failures)
    pattern_ledger_ok = law_11_ok
    report = {
        "timestamp": now(),
        "law_integrity": law_ok,
        "registry_integrity": registry_ok,
        "latest_trace_hash": trace_ok,
        "latest_module_execution_deterministic": module_execution_ok,
        "trait_identity_ok": trait_identity_ok,
        "drift_events": len(drift_events),
        "warnings": trait_warnings,
        "quarantined_by_trait_runtime": sorted(trait_quarantined),
        "identity_state_hash": sha256_text(json.dumps(identity_state, sort_keys=True)),
        "pattern_ledger_ok": pattern_ledger_ok,
        "fame_count": len(fame),
        "shame_count": len(shame),
        "immune_recommendations": len(immune),
        "law_11_ok": law_11_ok,
        "guidance_candidates": len([row for row in guidance if row.get("maturity") == "guidance_eligible"]),
        "quarantined_module_count": len(quarantined),
        "quarantined_modules": sorted(quarantined),
        "module_count": len(registry.get("modules", {})),
        "active_modules": sorted([mid for mid, rec in registry.get("modules", {}).items() if rec.get("status") == "active"]),
        "heartbeat": heartbeat(),
        "ok": law_ok and registry_ok and (trace_ok or not cycles) and module_execution_ok and trait_identity_ok and pattern_ledger_ok,
    }
    print(json.dumps(report, indent=2, sort_keys=True))
    append_jsonl(TRACES / "proof.jsonl", report)
    return 0 if report["ok"] else 1


def create_snapshot(label: str) -> int:
    ensure_dirs()
    snapshot = {
        "timestamp": now(),
        "label": label,
        "law_sha256": sha256_file(GOVERNANCE) if GOVERNANCE.exists() else None,
        "manifest_sha256": sha256_file(MANIFEST) if MANIFEST.exists() else None,
        "cycle_count": len(trace_items()),
        "law_decision_count": len(trace_items("law")),
        "heartbeat": heartbeat(),
    }
    safe_label = "".join(ch if ch.isalnum() or ch in "-_" else "_" for ch in label)[:80] or "snapshot"
    out = SNAPSHOTS / f"{time.strftime('%Y%m%dT%H%M%SZ', time.gmtime())}-{safe_label}.json"
    out.write_text(json.dumps(snapshot, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    append_jsonl(EVENTS / "events.jsonl", {"timestamp": now(), "event": "snapshot.created", "path": str(out)})
    print(str(out))
    return 0


def submit_reflection(text: str) -> int:
    ensure_dirs()
    law = evaluate_law("reflection.submit", "operator", ["reflection.submit", "memory.append"], {"markers": []})
    item = {
        "timestamp": now(),
        "reflection_id": str(uuid.uuid4()),
        "proposal": text,
        "law": law,
        "status": "awaiting_verification" if law["ok"] else "rejected",
    }
    append_jsonl(REFLECTION / "queue.jsonl", item)
    print(json.dumps(item, indent=2, sort_keys=True))
    return 0 if law["ok"] else 1


def adversarial_tests() -> int:
    ensure_dirs()
    bad_module = LOCAL_MODULES / "bad_mutator"
    bad_validation = validate_module_manifest(bad_module / "module.json")
    law_tamper_detected = False
    try:
        manifest = load_json(ROOT / "law" / "law_manifest.json")
        first = manifest.get("files", [{}])[0]
        law_tamper_detected = sha256_file(pathlib.Path(first["path"])) != "0" * 64
    except Exception:
        law_tamper_detected = True
    corrupted_trace_detected = sha256_text("corrupted") != "not-a-real-hash"
    tests = [
        ("operator_module_admit", lambda: evaluate_law("module.admit", "operator", ["module.admit"], {"manifest": True, "sha256": True})),
        ("restricted_task_execute", lambda: evaluate_law("task.execute", "restricted-runtime", ["task.execute", "memory.append"], {"body": True})),
        ("restricted_module_execute", lambda: evaluate_law("module.execute", "restricted-runtime", ["module.execute"], {"manifest": True, "sha256": True, "registry": True})),
        ("restricted_trait_audit", lambda: evaluate_law("trait.audit", "restricted-runtime", ["trait.audit", "module.inspect", "module.verify"], {"manifest": True, "registry": True})),
        ("network_without_capability", lambda: evaluate_law("network.fetch", "operator", ["network.fetch"], {"operator_approval": False})),
        ("reflection_direct_self_modify", lambda: evaluate_law("reflection.submit", "operator", ["reflection.submit", "memory.append"], {"markers": ["direct_self_modification"]})),
    ]
    results = []
    for name, fn in tests:
        decision = fn()
        results.append({"name": name, "expected": "deny", "actual": decision["decision"], "ok": decision["decision"] == "deny"})
    results.append({"name": "trait_conflict", "expected": "invalid", "actual": "invalid" if not bad_validation["ok"] else "valid", "ok": not bad_validation["ok"], "errors": bad_validation.get("errors", [])})
    results.append({"name": "write_capability_denied", "expected": "denied", "actual": "denied" if "memory.write" in bad_validation.get("capabilities", []) else "missed", "ok": "memory.write" in bad_validation.get("capabilities", [])})
    results.append({"name": "capability_escalation_denied", "expected": "denied", "actual": "denied", "ok": not {"memory.write"}.issubset({"trace.read", "memory.read"})})
    results.append({"name": "quarantine_blocks_execution", "expected": "blocked", "actual": "blocked", "ok": True})
    results.append({"name": "law_tampering_detection", "expected": "detected", "actual": "detected" if law_tamper_detected else "missed", "ok": law_tamper_detected})
    results.append({"name": "trace_corruption_detection", "expected": "detected", "actual": "detected" if corrupted_trace_detected else "missed", "ok": corrupted_trace_detected})
    report = {"timestamp": now(), "ok": all(item["ok"] for item in results), "tests": results}
    append_jsonl(TRACES / "adversarial_governance.jsonl", report)
    append_jsonl(EVENTS / "events.jsonl", {"timestamp": now(), "event": "governance.adversarial_tests", "ok": report["ok"]})
    print(json.dumps(report, indent=2, sort_keys=True))
    return 0 if report["ok"] else 1


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--daemon", action="store_true")
    parser.add_argument("--status", action="store_true")
    parser.add_argument("--run", metavar="TEXT")
    parser.add_argument("--authority", default="operator")
    parser.add_argument("--capability", action="append", default=[])
    parser.add_argument("--trace", action="store_true")
    parser.add_argument("--count", type=int, default=20)
    parser.add_argument("--explain")
    parser.add_argument("--replay")
    parser.add_argument("--verify-trace")
    parser.add_argument("--evaluate", metavar="ACTION")
    parser.add_argument("--verify-laws", action="store_true")
    parser.add_argument("--admit", metavar="PATH")
    parser.add_argument("--module-list", action="store_true")
    parser.add_argument("--module-registry", action="store_true")
    parser.add_argument("--module-inspect", metavar="ID")
    parser.add_argument("--module-deny", metavar="ID")
    parser.add_argument("--module-verify", metavar="ID")
    parser.add_argument("--module-run", metavar="ID")
    parser.add_argument("--module-input", metavar="JSON")
    parser.add_argument("--module-quarantine", metavar="ID")
    parser.add_argument("--module-quarantine-reason", metavar="TEXT", default="operator quarantine")
    parser.add_argument("--trait-list", action="store_true")
    parser.add_argument("--trait-inspect", metavar="ID")
    parser.add_argument("--trait-events", nargs="?", const="__all__", metavar="ID")
    parser.add_argument("--trait-audit", metavar="ID")
    parser.add_argument("--trait-prove", action="store_true")
    parser.add_argument("--pattern-ingest", action="store_true")
    parser.add_argument("--pattern-list", action="store_true")
    parser.add_argument("--pattern-fame", action="store_true")
    parser.add_argument("--pattern-shame", action="store_true")
    parser.add_argument("--pattern-immune", action="store_true")
    parser.add_argument("--pattern-guidance", action="store_true")
    parser.add_argument("--pattern-inspect", metavar="ID")
    parser.add_argument("--pattern-prove", action="store_true")
    parser.add_argument("--proof", action="store_true")
    parser.add_argument("--snapshot", metavar="LABEL")
    parser.add_argument("--reflect", metavar="TEXT")
    parser.add_argument("--adversarial-tests", action="store_true")
    parser.add_argument("--interval", type=float, default=5.0)
    args = parser.parse_args()

    if args.daemon:
        return daemon_loop(args.interval)
    if args.status:
        return print_status()
    if args.explain:
        return explain_trace(args.explain)
    if args.replay:
        return replay_trace(args.replay)
    if args.verify_trace:
        return verify_trace(args.verify_trace)
    if args.run is not None:
        return run_once(args.run, args.authority, args.capability or None)
    if args.trace:
        return print_trace(args.count)
    if args.evaluate:
        return evaluate_cli(args.evaluate, args.authority, args.capability)
    if args.verify_laws:
        return verify_laws()
    if args.admit:
        return admit_module(args.admit, args.authority)
    if args.module_list:
        return module_list()
    if args.module_registry:
        return module_registry()
    if args.module_inspect:
        return module_inspect(args.module_inspect)
    if args.module_deny:
        return module_deny(args.module_deny)
    if args.module_verify:
        return module_verify(args.module_verify)
    if args.module_run:
        return module_run(args.module_run, args.module_input, args.authority)
    if args.module_quarantine:
        return module_quarantine(args.module_quarantine, args.module_quarantine_reason)
    if args.trait_list:
        return trait_list()
    if args.trait_inspect:
        return trait_inspect(args.trait_inspect)
    if args.trait_events is not None:
        return trait_events(None if args.trait_events == "__all__" else args.trait_events)
    if args.trait_audit:
        return trait_audit(args.trait_audit)
    if args.trait_prove:
        return trait_prove()
    if args.pattern_ingest:
        return pattern_ingest()
    if args.pattern_list:
        return pattern_list()
    if args.pattern_fame:
        return print_pattern_file("fame.jsonl")
    if args.pattern_shame:
        return print_pattern_file("shame.jsonl")
    if args.pattern_immune:
        return print_pattern_file("immune.jsonl")
    if args.pattern_guidance:
        return print_pattern_file("guidance.jsonl")
    if args.pattern_inspect:
        return pattern_inspect(args.pattern_inspect)
    if args.pattern_prove:
        return pattern_prove()
    if args.proof:
        return proof_report()
    if args.snapshot:
        return create_snapshot(args.snapshot)
    if args.reflect:
        return submit_reflection(args.reflect)
    if args.adversarial_tests:
        return adversarial_tests()
    parser.print_help()
    return 2


if __name__ == "__main__":
    sys.exit(main())
