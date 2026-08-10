from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Protocol
from datetime import datetime
import json
import hashlib
import uuid


class EvidenceBundleProtocol(Protocol):
    """Protocol for evidence bundles - allows CCM to be independent of specific spec implementations."""
    def to_dict(self) -> dict: ...
    def all_passed(self) -> bool: ...


@dataclass
class VerificationReport:
    bundle: EvidenceBundleProtocol
    verified: bool
    verification_id: str
    timestamp: str
    verifier: str
    notes: str = ""

    def to_dict(self) -> Dict[str, Any]:
        return {
            "verification_id": self.verification_id,
            "timestamp": self.timestamp,
            "verifier": self.verifier,
            "verified": self.verified,
            "bundle": self.bundle.to_dict(),
            "notes": self.notes,
        }

    def to_json(self, path: str) -> None:
        with open(path, "w") as f:
            json.dump(self.to_dict(), f, indent=2)

    @classmethod
    def from_json(cls, path: str) -> "VerificationReport":
        with open(path, "r") as f:
            data = json.load(f)
        return cls(
            bundle=data["bundle"],
            verified=data["verified"],
            verification_id=data["verification_id"],
            timestamp=data["timestamp"],
            verifier=data["verifier"],
            notes=data.get("notes", ""),
        )


class EvidenceStore:
    """Persistent store for evidence bundles and verification reports."""

    def __init__(self, base_path: str = "./evidence_store") -> None:
        import os
        self.base_path = base_path
        os.makedirs(base_path, exist_ok=True)

    def _hash_bundle(self, bundle: EvidenceBundleProtocol) -> str:
        data = json.dumps(bundle.to_dict(), sort_keys=True).encode()
        return hashlib.sha256(data).hexdigest()[:16]

    def store_bundle(self, bundle: EvidenceBundleProtocol) -> str:
        bundle_hash = self._hash_bundle(bundle)
        path = f"{self.base_path}/bundle_{bundle_hash}.json"
        with open(path, "w") as f:
            json.dump(bundle.to_dict(), f, indent=2)
        return bundle_hash

    def load_bundle(self, bundle_hash: str) -> Optional[Dict[str, Any]]:
        path = f"{self.base_path}/bundle_{bundle_hash}.json"
        try:
            with open(path, "r") as f:
                data = json.load(f)
            return data
        except FileNotFoundError:
            return None

    def store_verification(self, report: VerificationReport) -> str:
        path = f"{self.base_path}/verification_{report.verification_id}.json"
        report.to_json(path)
        return report.verification_id

    def load_verification(self, verification_id: str) -> Optional[VerificationReport]:
        path = f"{self.base_path}/verification_{verification_id}.json"
        try:
            return VerificationReport.from_json(path)
        except FileNotFoundError:
            return None

    def list_bundles(self) -> List[str]:
        import os
        return [f.replace("bundle_", "").replace(".json", "") for f in os.listdir(self.base_path) if f.startswith("bundle_")]

    def list_verifications(self) -> List[str]:
        import os
        return [f.replace("verification_", "").replace(".json", "") for f in os.listdir(self.base_path) if f.startswith("verification_")]


def verify_bundle(bundle: EvidenceBundleProtocol, verifier: str = "automated", notes: str = "") -> VerificationReport:
    """Verify an evidence bundle - all laws must pass."""
    verified = bundle.all_passed()
    return VerificationReport(
        bundle=bundle,
        verified=verified,
        verification_id=str(uuid.uuid4()),
        timestamp=datetime.utcnow().isoformat(),
        verifier=verifier,
        notes=notes,
    )