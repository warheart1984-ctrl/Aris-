"""
reasoning_exchange.py — ADMIT/REJECT reasoning node with sigil trust boundaries.
"""

from __future__ import annotations

import json
import time
import uuid
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import Any, Dict, List, Optional

from governance_invariant_engine import cogos_root
from mesh_identity import MeshIdentityStore, device_sigil


class Disposition(str, Enum):
    ADMIT = "ADMIT"
    REJECT = "REJECT"
    PENDING = "PENDING"


@dataclass
class ExchangeMessage:
    message_id: str
    from_sigil: str
    to_sigil: str
    kind: str
    payload: Dict[str, Any]
    timestamp: str = field(default_factory=lambda: time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()))
    disposition: Disposition = Disposition.PENDING
    reason: str = ""

    def to_dict(self) -> Dict[str, Any]:
        return {
            "message_id": self.message_id,
            "from_sigil": self.from_sigil,
            "to_sigil": self.to_sigil,
            "kind": self.kind,
            "payload": self.payload,
            "timestamp": self.timestamp,
            "disposition": self.disposition.value,
            "reason": self.reason,
        }


@dataclass
class ExchangeResult:
    message: ExchangeMessage
    admitted: bool


class ReasoningExchangeNode:
    def __init__(self) -> None:
        self.root = cogos_root()
        self.config_path = self.root / "config" / "mesh.json"
        self.inbox = self.root / "memory" / "mesh" / "inbox.jsonl"
        self.outbox = self.root / "memory" / "mesh" / "outbox.jsonl"
        self.trust_path = self.root / "memory" / "mesh" / "trusted_peers.jsonl"
        for p in (self.inbox, self.outbox, self.trust_path):
            p.parent.mkdir(parents=True, exist_ok=True)
        self.identity = MeshIdentityStore().load_or_create()

    def _config(self) -> Dict[str, Any]:
        if not self.config_path.exists():
            return {}
        return json.loads(self.config_path.read_text(encoding="utf-8-sig"))

    def _trusted_sigils(self) -> List[str]:
        cfg = self._config()
        trusted = list(cfg.get("trusted_peer_sigils", []))
        if self.trust_path.exists():
            for line in self.trust_path.read_text(encoding="utf-8").strip().splitlines():
                try:
                    row = json.loads(line)
                    if row.get("device_sigil"):
                        trusted.append(row["device_sigil"])
                except json.JSONDecodeError:
                    continue
        return list(set(trusted))

    def propose(
        self,
        payload: Dict[str, Any],
        *,
        kind: str = "reasoning_proposal",
        to_sigil: Optional[str] = None,
    ) -> ExchangeMessage:
        cfg = self._config()
        allowed_kinds = cfg.get("allowed_payload_kinds", ["reasoning_proposal"])
        if kind not in allowed_kinds:
            raise ValueError(f"payload kind not allowed: {kind}")

        msg = ExchangeMessage(
            message_id=uuid.uuid4().hex[:16],
            from_sigil=self.identity.device_sigil,
            to_sigil=to_sigil or self.identity.family_mesh_id,
            kind=kind,
            payload=payload,
        )
        with self.outbox.open("a", encoding="utf-8") as fh:
            fh.write(json.dumps(msg.to_dict()) + "\n")
        return msg

    def receive(self, raw: Dict[str, Any]) -> ExchangeResult:
        msg = ExchangeMessage(
            message_id=str(raw.get("message_id", uuid.uuid4().hex[:16])),
            from_sigil=str(raw.get("from_sigil", "")),
            to_sigil=str(raw.get("to_sigil", "")),
            kind=str(raw.get("kind", "reasoning_proposal")),
            payload=dict(raw.get("payload", {})),
            timestamp=str(raw.get("timestamp", "")),
        )
        result = self.evaluate(msg)
        msg.disposition = Disposition.ADMIT if result.admitted else Disposition.REJECT
        msg.reason = result.message.reason
        with self.inbox.open("a", encoding="utf-8") as fh:
            fh.write(json.dumps(msg.to_dict()) + "\n")
        return result

    def evaluate(self, msg: ExchangeMessage) -> ExchangeResult:
        cfg = self._config()
        violations: List[str] = []

        if len(json.dumps(msg.payload)) > int(cfg.get("max_message_bytes", 65536)):
            violations.append("payload too large")

        if not msg.from_sigil or len(msg.from_sigil) != 64:
            violations.append("invalid from_sigil")

        allowed_kinds = cfg.get("allowed_payload_kinds", [])
        if allowed_kinds and msg.kind not in allowed_kinds:
            violations.append(f"kind not allowed: {msg.kind}")

        if cfg.get("require_sigil_exchange") and msg.from_sigil != self.identity.device_sigil:
            trusted = self._trusted_sigils()
            if trusted and msg.from_sigil not in trusted:
                violations.append("peer sigil not in trust list")

        if msg.payload.get("bypass_governance"):
            violations.append("governance bypass in payload")

        admitted = len(violations) == 0
        msg.reason = "; ".join(violations) if violations else "ADMIT: sigil and policy OK"
        msg.disposition = Disposition.ADMIT if admitted else Disposition.REJECT
        return ExchangeResult(message=msg, admitted=admitted)

    def admit(self, msg: ExchangeMessage) -> ExchangeResult:
        result = self.evaluate(msg)
        if result.admitted:
            msg.disposition = Disposition.ADMIT
        return result

    def reject(self, msg: ExchangeMessage, reason: str) -> ExchangeResult:
        msg.disposition = Disposition.REJECT
        msg.reason = reason
        return ExchangeResult(message=msg, admitted=False)

    def trust_peer(self, peer_device_id: str, peer_sigil: Optional[str] = None) -> Dict[str, Any]:
        sigil = peer_sigil or device_sigil(peer_device_id)
        row = {
            "ts": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
            "device_id": peer_device_id,
            "device_sigil": sigil,
        }
        with self.trust_path.open("a", encoding="utf-8") as fh:
            fh.write(json.dumps(row) + "\n")
        return row

    def list_recent(self, limit: int = 20) -> Dict[str, Any]:
        def tail(path: Path) -> List[Dict[str, Any]]:
            if not path.exists():
                return []
            rows = []
            for line in path.read_text(encoding="utf-8").strip().splitlines()[-limit:]:
                try:
                    rows.append(json.loads(line))
                except json.JSONDecodeError:
                    continue
            return rows

        return {
            "identity": MeshIdentityStore().export_exchange_bundle(),
            "inbox": tail(self.inbox),
            "outbox": tail(self.outbox),
            "trusted_count": len(self._trusted_sigils()),
        }
