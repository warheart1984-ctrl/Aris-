"""Canonical state packet: AAIS cycle truth with CoGOS proof as a derived view."""

from __future__ import annotations

import importlib.util
import uuid
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Mapping

_SCHEMA_PATH = Path(__file__).with_name("state_hash.py")
_spec = importlib.util.spec_from_file_location("cogos_state_hash", _SCHEMA_PATH)
assert _spec and _spec.loader
_sigil_mod = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(_sigil_mod)
sigil_binding_from_packet = _sigil_mod.sigil_binding_from_packet

SCHEMA_VERSION = "canonical-state-packet.v1"
DEFAULT_RUNTIME_LAW = "1001"
DEFAULT_AGENT_ID = "project-infi-governor"


def _utc_now() -> str:
    return datetime.now(UTC).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def debt_record_from_mapping(data: Mapping[str, Any] | None) -> dict[str, int]:
    payload = dict(data or {})
    trauma = int(payload.get("trauma") or 0)
    desire = int(payload.get("desire") or 0)
    truth = int(payload.get("truth") or 0)
    coupling = int(payload.get("coupling") or 0)
    scar = int(payload.get("scar") or 0)
    return {
        "trauma": max(0, trauma),
        "desire": max(0, desire),
        "truth": max(0, truth),
        "coupling": max(0, coupling),
        "scar": max(0, scar),
        "total": max(0, trauma + desire + truth + coupling + scar),
    }


def invariants_from_cogos_report(report: Mapping[str, Any]) -> list[dict[str, Any]]:
    checks = [
        ("law_integrity", bool(report.get("law_integrity"))),
        ("pid1_gate_ok", bool(report.get("pid1_gate_ok"))),
        ("registry_integrity", bool(report.get("registry_integrity"))),
        ("latest_trace_hash", bool(report.get("latest_trace_hash"))),
        ("trait_identity_ok", bool(report.get("trait_identity_ok"))),
        ("pattern_ledger_ok", bool(report.get("pattern_ledger_ok"))),
        ("ul_runtime_ok", bool(report.get("ul_runtime_ok"))),
        ("ul_substrate_gate_ok", bool(report.get("ul_substrate_gate_ok"))),
        ("voss_runtime_ok", bool(report.get("voss_runtime_ok"))),
        ("voss_golden_path_ok", bool(report.get("voss_golden_path_ok"))),
        ("voss_verifier_ok", bool(report.get("voss_verifier_ok"))),
        ("voss_binding_ok", bool(report.get("voss_binding_ok"))),
    ]
    return [{"id": name, "name": name, "satisfied": ok} for name, ok in checks]


def attach_sigil_binding(packet: dict[str, Any]) -> dict[str, Any]:
    merged = dict(packet)
    binding = sigil_binding_from_packet(merged)
    merged["sigil_binding"] = binding
    meta = dict(merged.get("meta_registers") or {})
    meta["META_SIGIL"] = binding["lambda_sigil_sha256"]
    meta["state_hash_sha256"] = binding["state_hash_sha256"]
    merged["meta_registers"] = meta
    views = dict(merged.get("views") or {})
    cogos_view = dict(views.get("cogos_proof") or {})
    cogos_view["sigil_binding"] = binding
    views["cogos_proof"] = cogos_view
    merged["views"] = views
    return merged


def cogos_proof_view(canonical: Mapping[str, Any], cogos_report: Mapping[str, Any]) -> dict[str, Any]:
    ul_voss = dict(cogos_report.get("ul_voss") or {})
    return {
        "schema_version": SCHEMA_VERSION,
        "packet_id": canonical.get("packet_id"),
        "timestamp": cogos_report.get("timestamp") or canonical.get("timestamp"),
        "cycle": canonical.get("cycle"),
        "runtime_law": canonical.get("runtime_law"),
        "ok": bool(cogos_report.get("ok")),
        "law_integrity": bool(cogos_report.get("law_integrity")),
        "pid1_gate_ok": bool(cogos_report.get("pid1_gate_ok")),
        "registry_integrity": bool(cogos_report.get("registry_integrity")),
        "latest_trace_hash": bool(cogos_report.get("latest_trace_hash")),
        "trait_identity_ok": bool(cogos_report.get("trait_identity_ok")),
        "pattern_ledger_ok": bool(cogos_report.get("pattern_ledger_ok")),
        "ul_runtime_ok": bool(cogos_report.get("ul_runtime_ok")),
        "ul_substrate_gate_ok": bool(cogos_report.get("ul_substrate_gate_ok")),
        "ul_latest_run_ok": bool(cogos_report.get("ul_latest_run_ok")),
        "voss_runtime_ok": bool(cogos_report.get("voss_runtime_ok")),
        "voss_golden_path_ok": bool(cogos_report.get("voss_golden_path_ok")),
        "voss_verifier_ok": bool(cogos_report.get("voss_verifier_ok")),
        "voss_binding_ok": bool(cogos_report.get("voss_binding_ok")),
        "ul_voss": ul_voss,
        "quarantined_modules": list(cogos_report.get("quarantined_modules") or []),
        "active_modules": list(cogos_report.get("active_modules") or []),
        "heartbeat": dict(cogos_report.get("heartbeat") or {}),
        "canonical_ref": canonical.get("packet_id"),
    }


def merge_cogos_proof(
    canonical: dict[str, Any],
    cogos_report: Mapping[str, Any],
    *,
    trace_id: str = "",
) -> dict[str, Any]:
    merged = dict(canonical)
    if trace_id:
        merged["trace_id"] = trace_id
    merged["invariants"] = invariants_from_cogos_report(cogos_report)
    merged["views"] = {
        "cogos_proof": cogos_proof_view(merged, cogos_report),
        "ul_voss": dict(cogos_report.get("ul_voss") or merged.get("views", {}).get("ul_voss") or {}),
    }
    return attach_sigil_binding(merged)


def build_from_cogos_report(
    cogos_report: Mapping[str, Any],
    *,
    host_meta: Mapping[str, Any] | None = None,
    state_registers: Mapping[str, Any] | None = None,
    cycle: int = 0,
    runtime_law: str = DEFAULT_RUNTIME_LAW,
) -> dict[str, Any]:
    registers = {
        "binary_state": runtime_law,
        "mode": "NORMAL" if cogos_report.get("ok") else "DEGRADED",
        "bound_flag": bool(cogos_report.get("pid1_gate_ok")),
        "fracture_mode": not bool(cogos_report.get("trait_identity_ok")),
        "operator_review_required": bool(cogos_report.get("quarantined_modules")),
    }
    registers.update(dict(state_registers or {}))
    base = {
        "schema_version": SCHEMA_VERSION,
        "packet_id": str(uuid.uuid4()),
        "timestamp": str(cogos_report.get("timestamp") or _utc_now()),
        "cycle": cycle,
        "runtime_law": runtime_law,
        "state_registers": registers,
        "meta_registers": {
            "host": dict(host_meta or {"name": "cogos-live", "host_class": "external", "version": "0"}),
            "governor_version": str((cogos_report.get("heartbeat") or {}).get("version") or "0.12"),
            "substrate": "cogos",
        },
        "debt_record": debt_record_from_mapping({}),
        "risk_profile": int(cogos_report.get("drift_events") or 0),
        "prime_depth": 0,
        "invariants": invariants_from_cogos_report(cogos_report),
        "trace_id": "",
        "agent_id": DEFAULT_AGENT_ID,
        "event_log_window": [],
        "cycle_disposition": "SUCCESS" if cogos_report.get("ok") else "REJECTED",
        "sigil_binding": {},
        "views": {"cogos_proof": {}, "ul_voss": {}},
    }
    return merge_cogos_proof(base, cogos_report)
