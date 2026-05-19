"""AAIS / Voss deterministic canonical state hashing (sigil.docx)."""

from __future__ import annotations

import hashlib
import json
import struct
import uuid
from typing import Any, Mapping

DOMAIN_SEPARATOR = "AAIS_STATE_V1"
SIGIL_INTENT_PHRASE = "zeronullnullzero 1001"
LAMBDA_SIGIL_SHA256 = hashlib.sha256(SIGIL_INTENT_PHRASE.encode("utf-8")).hexdigest()
SIGIL_ENFORCEMENT_CYCLE = 1001
EVENT_LOG_WINDOW_MAX = 32

_RUNTIME_LAW_INT = {"0001": 1, "1000": 1000, "1001": 1001, "1010": 1010, "1111": 1111}


def _to_be_u64(value: int) -> bytes:
    return struct.pack(">Q", int(value))


def _canonical_json(obj: Any) -> bytes:
    return json.dumps(obj, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode("utf-8")


def _sort_invariants(items: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return sorted(items, key=lambda row: str(row.get("name") or row.get("id") or ""))


def _sort_events(events: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return sorted(events, key=lambda row: int(row.get("t") or row.get("timestamp") or 0))


def _id_to_32_bytes(value: Any) -> bytes:
    if isinstance(value, bytes):
        raw = value
    elif isinstance(value, str):
        text = value.replace("-", "").strip()
        if len(text) == 64 and all(c in "0123456789abcdefABCDEF" for c in text):
            raw = bytes.fromhex(text)
        else:
            raw = uuid.UUID(text).bytes if len(text) == 36 else hashlib.sha256(text.encode()).digest()
    else:
        raw = hashlib.sha256(str(value).encode()).digest()
    if len(raw) != 32:
        raw = hashlib.sha256(raw).digest()
    return raw


def _timestamp_to_epoch(value: Any) -> int:
    if isinstance(value, (int, float)):
        return int(value)
    text = str(value or "").strip()
    if not text:
        return 0
    if text.endswith("Z"):
        text = text[:-1] + "+00:00"
    try:
        from datetime import datetime

        return int(datetime.fromisoformat(text).timestamp())
    except ValueError:
        return 0


def _runtime_law_int(runtime_law: Any) -> int:
    if isinstance(runtime_law, int):
        return runtime_law
    text = str(runtime_law or "1001")
    if text.isdigit():
        return int(text)
    return _RUNTIME_LAW_INT.get(text, 1001)


def hashable_state_from_packet(packet: Mapping[str, Any]) -> dict[str, Any]:
    events = list(packet.get("event_log_window") or [])[-EVENT_LOG_WINDOW_MAX:]
    canonical_events: list[dict[str, Any]] = []
    for row in events:
        if not isinstance(row, dict):
            continue
        canonical_events.append(
            {
                "t": _timestamp_to_epoch(row.get("t") or row.get("timestamp")),
                "k": str(row.get("k") or row.get("event") or row.get("kind") or "event"),
                "p": dict(
                    row.get("p")
                    or row.get("payload")
                    or {
                        k: v
                        for k, v in row.items()
                        if k not in {"t", "timestamp", "k", "event", "kind", "p", "payload"}
                    }
                ),
            }
        )
    risk = packet.get("risk_profile")
    return {
        "cycle": int(packet.get("cycle") or 0),
        "runtime_law": _runtime_law_int(packet.get("runtime_law")),
        "state_registers": dict(packet.get("state_registers") or {}),
        "meta_registers": dict(packet.get("meta_registers") or {}),
        "debt_record": dict(packet.get("debt_record") or {}),
        "risk_profile": {"value": int(risk)} if not isinstance(risk, dict) else dict(risk),
        "prime_depth": int(packet.get("prime_depth") or 0),
        "invariants": [dict(row) for row in list(packet.get("invariants") or []) if isinstance(row, dict)],
        "trace_id": _id_to_32_bytes(packet.get("trace_id") or packet.get("packet_id") or uuid.uuid4()),
        "agent_id": _id_to_32_bytes(packet.get("agent_id") or "project-infi-governor"),
        "timestamp": _timestamp_to_epoch(packet.get("timestamp")),
        "event_log_window": canonical_events,
    }


def canonical_state_bytes(state: Mapping[str, Any]) -> bytes:
    chunks: list[bytes] = []

    def add_field(tag: int, payload: bytes) -> None:
        chunks.append(struct.pack("B", tag))
        chunks.append(struct.pack(">I", len(payload)))
        chunks.append(payload)

    add_field(0x01, DOMAIN_SEPARATOR.encode("utf-8"))
    add_field(0x02, _to_be_u64(int(state["cycle"])))
    add_field(0x03, _to_be_u64(_runtime_law_int(state["runtime_law"])))
    add_field(0x04, _canonical_json(state.get("state_registers", {})))
    add_field(0x05, _canonical_json(state.get("meta_registers", {})))
    add_field(0x06, _canonical_json(state.get("debt_record", {})))
    add_field(0x07, _canonical_json(state.get("risk_profile", {})))
    add_field(0x08, _to_be_u64(int(state.get("prime_depth", 0))))
    add_field(0x09, _canonical_json(_sort_invariants(list(state.get("invariants", [])))))
    add_field(0x0A, _id_to_32_bytes(state["trace_id"]))
    add_field(0x0B, _id_to_32_bytes(state["agent_id"]))
    add_field(0x0C, _to_be_u64(int(state["timestamp"])))
    add_field(0x0D, _canonical_json(_sort_events(list(state.get("event_log_window", [])))))
    return b"".join(chunks)


def state_hash_sha256(state: Mapping[str, Any]) -> str:
    return hashlib.sha256(canonical_state_bytes(state)).hexdigest()


def sigil_binding_from_packet(packet: Mapping[str, Any]) -> dict[str, Any]:
    hashable = hashable_state_from_packet(packet)
    current_hash = state_hash_sha256(hashable)
    cycle = int(packet.get("cycle") or 0)
    enforcement_required = cycle == SIGIL_ENFORCEMENT_CYCLE or str(packet.get("runtime_law")) == "1001"
    sigil_match = current_hash == LAMBDA_SIGIL_SHA256
    return {
        "document": "sigil.docx",
        "intent_phrase": SIGIL_INTENT_PHRASE,
        "lambda_sigil_sha256": LAMBDA_SIGIL_SHA256,
        "domain_separator": DOMAIN_SEPARATOR,
        "enforcement_cycle": SIGIL_ENFORCEMENT_CYCLE,
        "enforcement_required": enforcement_required,
        "state_hash_sha256": current_hash,
        "sigil_match": sigil_match,
        "status": "bound" if sigil_match else ("pending" if not enforcement_required else "SIGIL_MISMATCH_AT_1001"),
    }
