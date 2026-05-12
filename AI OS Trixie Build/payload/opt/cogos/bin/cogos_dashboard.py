#!/usr/bin/env python3
"""Local CoGOS governance dashboard."""

from __future__ import annotations

import html
import json
import pathlib
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import urlparse


ROOT = pathlib.Path("/opt/cogos")
RUN = pathlib.Path("/run")
MEMORY = ROOT / "memory"
TRACES = MEMORY / "traces"
LOGS = MEMORY / "logs"
EVENTS = MEMORY / "events"
SNAPSHOTS = MEMORY / "snapshots"
REFLECTION = MEMORY / "reflection"
MODULES = MEMORY / "modules"
TASKS = ROOT / "tasks"
REGISTRY = ROOT / "modules" / "registry.json"
RUNTIME_CONFIG = ROOT / "config" / "runtime.json"
BOOT_PROFILE = ROOT / "config" / "boot_profile.json"
PATTERNS = MEMORY / "patterns"


def read_json(path: pathlib.Path, default):
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return default


def read_jsonl(path: pathlib.Path, limit: int = 20):
    if not path.exists():
        return []
    rows = []
    for line in path.read_text(encoding="utf-8", errors="replace").splitlines():
        try:
            rows.append(json.loads(line))
        except Exception:
            pass
    return rows[-limit:]


def count_files(path: pathlib.Path) -> int:
    try:
        return len([p for p in path.iterdir() if p.is_file()])
    except Exception:
        return 0


def read_text(path: pathlib.Path, default: str = "") -> str:
    try:
        return path.read_text(encoding="utf-8", errors="replace").strip()
    except Exception:
        return default


def pid_running(path: pathlib.Path) -> bool:
    try:
        pid = path.read_text(encoding="utf-8").strip()
        if not pid:
            return False
        return pathlib.Path(f"/proc/{pid}").exists()
    except Exception:
        return False


def dashboard_data():
    cycles = read_jsonl(TRACES / "aris_cycles.jsonl", 50)
    laws = read_jsonl(TRACES / "law_decisions.jsonl", 50)
    registry = read_json(REGISTRY, {"modules": {}})
    denials = [x for x in laws if x.get("decision") == "deny"]
    module_executions = read_jsonl(MODULES / "executions.jsonl", 20)
    sandbox_denials = read_jsonl(MODULES / "sandbox_denials.jsonl", 20)
    trait_events = read_jsonl(MODULES / "trait_events.jsonl", 30)
    drift = read_jsonl(MODULES / "drift.jsonl", 30)
    identity_state = read_json(MODULES / "identity_state.json", {"modules": {}})
    trait_proof = read_jsonl(MODULES / "trait_proof.jsonl", 5)
    pattern_events = read_jsonl(PATTERNS / "events.jsonl", 50)
    fame = read_jsonl(PATTERNS / "fame.jsonl", 30)
    shame = read_jsonl(PATTERNS / "shame.jsonl", 30)
    immune = read_jsonl(PATTERNS / "immune.jsonl", 30)
    guidance = read_jsonl(PATTERNS / "guidance.jsonl", 30)
    pattern_proof = read_jsonl(PATTERNS / "proof.jsonl", 5)
    proof = read_jsonl(TRACES / "proof.jsonl", 5)
    quarantined = {
        mid: rec for mid, rec in registry.get("modules", {}).items()
        if rec.get("status") == "quarantined"
    }
    return {
        "daemon": read_json(RUN / "cogos-daemon.json", {"status": "unknown"}),
        "boot_profile": read_json(BOOT_PROFILE, {}),
        "performance": {
            "loadavg": read_text(pathlib.Path("/proc/loadavg"), "unknown"),
            "meminfo": "\n".join(read_text(pathlib.Path("/proc/meminfo"), "").splitlines()[:5]),
            "dashboard_running": pid_running(RUN / "cogos-dashboard.pid"),
            "daemon_running": pid_running(RUN / "cogos-daemon.pid"),
        },
        "heartbeat": read_json(LOGS / "heartbeat.json", {}),
        "queue": {
            "inbox": count_files(TASKS / "inbox"),
            "done": count_files(TASKS / "done"),
            "failed": count_files(TASKS / "failed"),
        },
        "cycles": cycles,
        "law_decisions": laws,
        "approvals": len([x for x in laws if x.get("decision") == "approve"]),
        "denials": len([x for x in laws if x.get("decision") == "deny"]),
        "events": read_jsonl(EVENTS / "events.jsonl", 50),
        "reflections": read_jsonl(REFLECTION / "queue.jsonl", 20),
        "snapshots": sorted([p.name for p in SNAPSHOTS.glob("*.json")])[-20:] if SNAPSHOTS.exists() else [],
        "modules": read_jsonl(MODULES / "admission.jsonl", 20),
        "module_registry": registry,
        "trait_ledger": read_jsonl(MODULES / "trait_ledger.jsonl", 20),
        "module_verifications": read_jsonl(MODULES / "verification.jsonl", 20),
        "module_executions": module_executions,
        "latest_module_output": module_executions[-1].get("output", {}) if module_executions else {},
        "sandbox_denials": sandbox_denials,
        "sandbox_status": read_json(RUNTIME_CONFIG, {}).get("sandbox", {}),
        "trait_runtime": read_json(RUNTIME_CONFIG, {}).get("trait_runtime", {}),
        "identity_state": identity_state,
        "trait_events": trait_events,
        "drift": drift,
        "trait_warnings": [row for row in drift if row.get("issues")],
        "trait_proof": trait_proof[-1] if trait_proof else {},
        "pattern_ledger": pattern_events,
        "fame": fame,
        "shame": shame,
        "immune": immune,
        "guidance": guidance,
        "pattern_proof": pattern_proof[-1] if pattern_proof else {},
        "severity_counts": {sev: len([row for row in shame if row.get("severity") == sev]) for sev in ["S1", "S2", "S3", "S4", "S5"]},
        "quarantined_modules": quarantined,
        "v9_proof": proof[-1] if proof else {},
        "latest_denials": denials[-10:],
        "verifications": read_jsonl(TRACES / "verifications.jsonl", 20),
        "law_integrity": read_jsonl(TRACES / "law_integrity.jsonl", 5),
        "recovery_hints": [
            "Run cogos-doctor for a full local diagnosis.",
            "Run cogos-operator for the fast v10 operator surface.",
            "Run cogos-perf to inspect VM pressure and dashboard state.",
            "Run cogos-dashboard-start only when you need the web UI.",
            "Run cogos-dashboard-stop if Puppy becomes laggy.",
            "Run cogos-daemon --verify-laws if law integrity is empty or false.",
            "Run cogos-verify-trace latest after a governed cycle.",
            "Run cogos-module verify <id> after admitting a module.",
            "Run cogos-module run <id> to execute an admitted module through the sandbox.",
            "Run cogos-module quarantine <id> <reason> when a module should stop executing.",
            "Run cogos-traits audit <id> to inspect trait identity health.",
            "Run cogos-traits prove for trait identity proof.",
            "Run cogos-patterns ingest after module runs or denials.",
            "Run cogos-patterns prove for Pattern Ledger proof.",
        ],
    }


def card(title: str, body: str) -> str:
    return f"<section><h2>{html.escape(title)}</h2>{body}</section>"


def pre(obj) -> str:
    return "<pre>" + html.escape(json.dumps(obj, indent=2, sort_keys=True)) + "</pre>"


def render() -> bytes:
    data = dashboard_data()
    hb = data["heartbeat"]
    load = hb.get("cognitive_load", {})
    body = [
        "<!doctype html><html><head><meta charset='utf-8'><meta http-equiv='refresh' content='5'>",
        "<title>CoGOS Governance Dashboard</title>",
        "<style>body{font-family:Arial,sans-serif;margin:0;background:#101418;color:#e9eef2}header{padding:20px 28px;background:#17202a;border-bottom:1px solid #2b3948}main{padding:20px;display:grid;grid-template-columns:repeat(auto-fit,minmax(320px,1fr));gap:14px}section{background:#18222d;border:1px solid #2c3b49;border-radius:6px;padding:14px}h1,h2{margin:0 0 10px}pre{white-space:pre-wrap;word-break:break-word;background:#0d1117;border:1px solid #2b3948;padding:10px;border-radius:4px;max-height:360px;overflow:auto}.metric{font-size:28px;font-weight:700}.ok{color:#78d98b}.bad{color:#ff8b8b}.muted{color:#9dadbc}</style>",
        "</head><body><header><h1>CoGOS Governance Dashboard</h1><div class='muted'>local runtime observability - refreshes every 5 seconds</div></header><main>",
        card("Daemon Health", f"<div class='metric'>{html.escape(str(data['daemon'].get('status', 'unknown')))}</div>{pre(data['daemon'])}"),
        card("Boot Profile", pre(data["boot_profile"])),
        card("Performance", pre(data["performance"])),
        card("Heartbeat", f"<div>cycles: <b>{hb.get('cycles', 0)}</b> - queue: <b>{hb.get('queue_depth', 0)}</b> - memory: <b>{html.escape(str(hb.get('memory_state', 'unknown')))}</b></div>{pre(hb)}"),
        card("Cognitive Load", f"<div class='metric'>{load.get('active_cycles', 0)} / {load.get('max_active_cycles', 6)}</div>{pre(load)}"),
        card("Queue", pre(data["queue"])),
        card("Law Decisions", f"<div><span class='ok'>approvals {data['approvals']}</span> · <span class='bad'>denials {data['denials']}</span></div>{pre(data['law_decisions'][-10:])}"),
        card("Recent Cycles", pre(data["cycles"][-10:])),
        card("Trace Verifications", pre(data["verifications"])),
        card("Law Integrity", pre(data["law_integrity"])),
        card("Module Registry", pre(data["module_registry"])),
        card("Module Admission History", pre(data["modules"])),
        card("Trait Ledger", pre(data["trait_ledger"])),
        card("Module Verifications", pre(data["module_verifications"])),
        card("Sandbox Status", pre(data["sandbox_status"])),
        card("Trait Runtime Policy", pre(data["trait_runtime"])),
        card("Identity State", pre(data["identity_state"])),
        card("Drift Score", pre({mid: item.get("drift_score", 0) for mid, item in data["identity_state"].get("modules", {}).items()})),
        card("Trait Warnings", pre(data["trait_warnings"])),
        card("Latest Trait Evidence", pre(data["trait_events"][-10:])),
        card("Drift History", pre(data["drift"][-10:])),
        card("Trait Proof", pre(data["trait_proof"])),
        card("Pattern Ledger", pre(data["pattern_ledger"][-15:])),
        card("Hall of Fame", pre(data["fame"][-10:])),
        card("Hall of Shame", pre(data["shame"][-10:])),
        card("Immune Recommendations", pre(data["immune"][-10:])),
        card("Severity Counts", pre(data["severity_counts"])),
        card("Guidance Candidates", pre(data["guidance"][-10:])),
        card("Pattern Proof", pre(data["pattern_proof"])),
        card("Recent Module Runs", pre(data["module_executions"])),
        card("Latest Module Output", pre(data["latest_module_output"])),
        card("Sandbox Denials", pre(data["sandbox_denials"])),
        card("Quarantined Modules", pre(data["quarantined_modules"])),
        card("V9 Proof State", pre(data["v9_proof"])),
        card("Latest Denials", pre(data["latest_denials"])),
        card("Reflections", pre(data["reflections"])),
        card("Snapshots", pre(data["snapshots"])),
        card("Event Bus", pre(data["events"][-15:])),
        card("Recovery Hints", pre(data["recovery_hints"])),
        "</main></body></html>",
    ]
    return "".join(body).encode("utf-8")


class Handler(BaseHTTPRequestHandler):
    def do_GET(self):
        parsed = urlparse(self.path)
        if parsed.path == "/api/status":
            payload = json.dumps(dashboard_data(), indent=2, sort_keys=True).encode("utf-8")
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(payload)))
            self.end_headers()
            self.wfile.write(payload)
            return
        if parsed.path not in ("/", "/index.html"):
            self.send_error(404)
            return
        payload = render()
        self.send_response(200)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Content-Length", str(len(payload)))
        self.end_headers()
        self.wfile.write(payload)

    def log_message(self, fmt, *args):
        return


def main() -> int:
    server = ThreadingHTTPServer(("127.0.0.1", 8080), Handler)
    server.serve_forever()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
