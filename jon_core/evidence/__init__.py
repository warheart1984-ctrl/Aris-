"""Evidence - Replay, Audit, Verification."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Callable
import json
import hashlib
import time


@dataclass
class ReplayResult:
    """Result of a replay operation."""
    replay_id: str
    original_record: Dict[str, Any]
    replayed_decision: Dict[str, Any]
    divergence: bool
    divergence_details: List[str] = field(default_factory=list)
    timestamp: float = field(default_factory=time.time)


class ReplayHarness:
    """Deterministic re-execution harness for evidence flows."""
    
    def __init__(self):
        self._replay_functions: Dict[str, Callable[[Dict[str, Any]], Dict[str, Any]]] = {}

    def register_replay(self, flow_name: str, function: Callable[[Dict[str, Any]], Dict[str, Any]]) -> None:
        self._replay_functions[flow_name] = function

    def replay(self, flow_name: str, ledger_entry: Dict[str, Any]) -> ReplayResult:
        """Re-execute governance decision from ledger record."""
        function = self._replay_functions.get(flow_name)
        if not function:
            return ReplayResult(
                replay_id="",
                original_record=ledger_entry,
                replayed_decision={},
                divergence=True,
                divergence_details=[f"No replay function for {flow_name}"],
            )
        
        try:
            replayed = function(ledger_entry.get("context", {}), ledger_entry.get("action", {}))
            original = ledger_entry.get("admission") or ledger_entry.get("decision") or {}
            
            divergence = False
            details = []
            
            # Compare key fields
            for key in ["allowed", "disposition", "reason", "verdict"]:
                if key in original and key in replayed:
                    if original[key] != replayed[key]:
                        divergence = True
                        details.append(f"{key}: original={original[key]}, replayed={replayed[key]}")
            
            return ReplayResult(
                replay_id=hashlib.sha256(str(time.time()).encode()).hexdigest()[:8],
                original_record=ledger_entry,
                replayed_decision=replayed,
                divergence=divergence,
                divergence_details=details,
            )
        except Exception as e:
            return ReplayResult(
                replay_id="",
                original_record=ledger_entry,
                replayed_decision={},
                divergence=True,
                divergence_details=[f"Replay error: {e}"],
            )


class AuditChainVerifier:
    """Verify audit chain integrity across GRE, LawLedger, Stabilization log."""
    
    def __init__(self):
        self._chains: Dict[str, List[Dict[str, Any]]] = {}

    def register_chain(self, name: str, records: List[Dict[str, Any]]) -> None:
        self._chains[name] = records

    def verify_chain(self, name: str) -> tuple[bool, List[str]]:
        records = self._chains.get(name, [])
        errors = []
        expected_prev = "0" * 64
        
        for i, record in enumerate(records):
            prev = record.get("previous_hash", "")
            if prev != expected_prev:
                errors.append(f"Record {i}: previous_hash mismatch")
            expected_prev = record.get("record_hash", "")
        
        return len(errors) == 0, errors

    def cross_verify(self, chain_names: List[str]) -> Dict[str, Any]:
        """Verify consistency across multiple chains."""
        results = {}
        for name in chain_names:
            valid, errors = self.verify_chain(name)
            results[name] = {"valid": valid, "errors": errors}
        
        # Check for gaps
        all_valid = all(r["valid"] for r in results.values())
        
        return {
            "all_valid": all_valid,
            "chains": results,
        }


@dataclass
class VerificationArtifacts:
    """Standardized verification artifacts for 1001 gate."""
    verification_type: str
    status_code: int
    score: float
    details: Dict[str, Any]
    logbook_entry_id: Optional[str] = None
    timestamp: float = field(default_factory=time.time)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "type": self.verification_type,
            "status_code": self.status_code,
            "score": self.score,
            "details": self.details,
            "logbook_entry_id": self.logbook_entry_id,
            "timestamp": self.timestamp,
        }


class VerificationEvidencePackager:
    """Package verification evidence for 1001 gate."""
    
    def package(
        self,
        artifacts: List[VerificationArtifacts],
        logbook_entry: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        return {
            "verification_artifacts": [a.to_dict() for a in artifacts],
            "logbook_correlation": logbook_entry,
            "packaged_at": time.time(),
            "artifact_count": len(artifacts),
        }