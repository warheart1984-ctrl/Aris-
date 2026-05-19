"""
net_gre.py — Network governance bridge (Phase 1 skeleton).

All outbound/inbound flow metadata should pass policy checks before modules act.
"""

from __future__ import annotations

import json
import re
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional

from governance_invariant_engine import Severity, cogos_root


@dataclass
class NetFlow:
    direction: str  # outbound | inbound
    protocol: str
    host: str
    port: int = 0
    module_id: str = "unknown"
    profile_id: str = "operator"
    metadata: Dict[str, Any] = field(default_factory=dict)


@dataclass
class NetPolicyResult:
    allowed: bool
    violations: List[str] = field(default_factory=list)
    severity: str = "LOW"


class NetGRE:
    """Fail-closed network policy evaluator."""

    FORBIDDEN_HOST_PATTERNS = [
        re.compile(r"^\s*$"),
    ]
    CLEARTEXT_AUTH_PATTERNS = [
        re.compile(r"password\s*=", re.I),
        re.compile(r"Authorization:\s*Basic\s+", re.I),
    ]

    def __init__(self) -> None:
        self.log_path = cogos_root() / "memory" / "traces" / "net_gre.jsonl"

    def evaluate(self, flow: NetFlow) -> NetPolicyResult:
        violations: List[str] = []

        if not flow.host or flow.host.strip() == "":
            violations.append("empty host")

        if flow.direction == "outbound" and flow.port in (23, 21):
            violations.append(f"cleartext legacy port {flow.port}")

        for pat in self.CLEARTEXT_AUTH_PATTERNS:
            blob = json.dumps(flow.metadata, default=str)
            if pat.search(blob):
                violations.append("cleartext credential pattern in metadata")

        if flow.profile_id == "kid" and flow.direction == "outbound":
            if flow.port not in (0, 80, 443) and flow.port > 0:
                violations.append("kid profile: non-standard outbound port")

        allowed = len(violations) == 0
        severity = Severity.CRITICAL.value if not allowed else Severity.LOW.value
        result = NetPolicyResult(allowed=allowed, violations=violations, severity=severity)
        self._log(flow, result)
        return result

    def _log(self, flow: NetFlow, result: NetPolicyResult) -> None:
        self.log_path.parent.mkdir(parents=True, exist_ok=True)
        row = {
            "ts": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
            "flow": {
                "direction": flow.direction,
                "protocol": flow.protocol,
                "host": flow.host,
                "port": flow.port,
                "module_id": flow.module_id,
                "profile_id": flow.profile_id,
            },
            "allowed": result.allowed,
            "violations": result.violations,
        }
        with self.log_path.open("a", encoding="utf-8") as fh:
            fh.write(json.dumps(row) + "\n")
