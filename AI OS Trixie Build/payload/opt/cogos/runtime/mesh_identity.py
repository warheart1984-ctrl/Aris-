"""
mesh_identity.py — Device/family identity keys bound to Λ-sigil lineage.
"""

from __future__ import annotations

import hashlib
import json
import os
import socket
import time
import uuid
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, List, Optional

from governance_invariant_engine import cogos_root

try:
    from state_hash import LAMBDA_SIGIL_SHA256
except ImportError:
    LAMBDA_SIGIL_SHA256 = hashlib.sha256(b"zeronullnullzero 1001").hexdigest()


@dataclass
class MeshIdentity:
    device_id: str
    device_sigil: str
    lambda_anchor: str
    hostname: str
    family_mesh_id: str
    created_at: str


def _hostname() -> str:
    try:
        return socket.gethostname()
    except OSError:
        return "unknown"


def device_sigil(device_id: str, lambda_anchor: str = LAMBDA_SIGIL_SHA256) -> str:
    blob = f"{lambda_anchor}:{device_id}:infi-mesh-v1"
    return hashlib.sha256(blob.encode("utf-8")).hexdigest()


def family_mesh_id(device_sigil_hex: str, mesh_name: str = "infi-family") -> str:
    return hashlib.sha256(f"{mesh_name}:{device_sigil_hex}".encode("utf-8")).hexdigest()[:32]


class MeshIdentityStore:
    def __init__(self, path: Optional[Path] = None) -> None:
        self.path = path or (cogos_root() / "memory" / "mesh" / "identity.json")
        self.path.parent.mkdir(parents=True, exist_ok=True)

    def load_or_create(self) -> MeshIdentity:
        if self.path.exists():
            data = json.loads(self.path.read_text(encoding="utf-8-sig"))
            return MeshIdentity(**data)
        device_id = os.environ.get("COGOS_DEVICE_ID", uuid.uuid4().hex[:16])
        sigil = device_sigil(device_id)
        ident = MeshIdentity(
            device_id=device_id,
            device_sigil=sigil,
            lambda_anchor=LAMBDA_SIGIL_SHA256,
            hostname=_hostname(),
            family_mesh_id=family_mesh_id(sigil),
            created_at=time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        )
        self.save(ident)
        return ident

    def save(self, ident: MeshIdentity) -> None:
        self.path.write_text(
            json.dumps(
                {
                    "device_id": ident.device_id,
                    "device_sigil": ident.device_sigil,
                    "lambda_anchor": ident.lambda_anchor,
                    "hostname": ident.hostname,
                    "family_mesh_id": ident.family_mesh_id,
                    "created_at": ident.created_at,
                },
                indent=2,
            )
            + "\n",
            encoding="utf-8",
        )

    def export_exchange_bundle(self) -> Dict[str, Any]:
        ident = self.load_or_create()
        return {
            "device_id": ident.device_id,
            "device_sigil": ident.device_sigil,
            "family_mesh_id": ident.family_mesh_id,
            "lambda_anchor": ident.lambda_anchor,
            "hostname": ident.hostname,
        }
