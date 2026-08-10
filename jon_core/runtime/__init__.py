"""Runtime - ULRuntimeSubstrate, BootstrapLaw, LawSpine, Runtime Profiles, Desktop Bootstrap."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Callable
import hashlib
import json
import time


@dataclass
class LawSpineSnapshot:
    """Immutable law spine snapshot."""
    manifest: Dict[str, Any]
    manifest_hash: str
    expected_hash: str
    frozen: bool
    ok: bool


class LawSpine:
    """Immutable root law manifest with SHA256 verification."""
    
    def __init__(self, manifest: Dict[str, Any]):
        self._manifest = manifest
        self._expected_hash = self._compute_hash(manifest)
        self._frozen = True

    def _compute_hash(self, manifest: Dict[str, Any]) -> str:
        content = json.dumps(manifest, sort_keys=True, separators=(",", ":"))
        return hashlib.sha256(content.encode("utf-8")).hexdigest()

    def snapshot(self) -> LawSpineSnapshot:
        current_hash = self._compute_hash(self._manifest)
        return LawSpineSnapshot(
            manifest=self._manifest,
            manifest_hash=current_hash,
            expected_hash=self._expected_hash,
            frozen=self._frozen,
            ok=current_hash == self._expected_hash,
        )

    def get_manifest(self) -> Dict[str, Any]:
        return self._manifest.copy()

    def verify(self) -> bool:
        return self.snapshot().ok


class BootstrapLaw:
    """Loads LawSpine at startup; verifies manifest hash."""
    
    def __init__(self, law_spine: LawSpine):
        self._law_spine = law_spine
        self._ok = False
        self._reason = ""

    def execute(self) -> tuple[bool, str]:
        snapshot = self._law_spine.snapshot()
        if not snapshot.ok:
            self._ok = False
            self._reason = f"Manifest hash mismatch: {snapshot.manifest_hash} != {snapshot.expected_hash}"
        else:
            self._ok = True
            self._reason = "LawSpine verified"
        return self._ok, self._reason

    @property
    def ok(self) -> bool:
        return self._ok

    @property
    def reason(self) -> str:
        return self._reason


@dataclass
class RuntimeProfile:
    """Runtime profile with feature flags."""
    profile_id: str
    evolving_engine_active: bool = True
    repo_changes_blocked: bool = False
    risky_paths_require_manual_upgrade: bool = False
    route_sequence: List[str] = field(default_factory=lambda: [
        "Jarvis Blueprint",
        "Operator", 
        "Forge",
        "Forge Eval",
        "UL Runtime",
        "Outcome",
    ])
    feature_flags: Dict[str, Any] = field(default_factory=dict)


class ProfileRegistry:
    """Profile system factory."""
    
    def __init__(self):
        self._profiles: Dict[str, RuntimeProfile] = {}
        self._register_defaults()

    def _register_defaults(self) -> None:
        self._profiles["v2"] = RuntimeProfile(
            profile_id="v2",
            evolving_engine_active=True,
            repo_changes_blocked=False,
            risky_paths_require_manual_upgrade=False,
            route_sequence=[
                "Jarvis Blueprint",
                "Operator",
                "Forge", 
                "Forge Eval",
                "UL Runtime",
                "Outcome",
            ],
        )
        
        self._profiles["v2-strict"] = RuntimeProfile(
            profile_id="v2-strict",
            evolving_engine_active=True,
            repo_changes_blocked=True,
            risky_paths_require_manual_upgrade=True,
            route_sequence=[
                "Jarvis Blueprint",
                "Operator",
                "Forge",
                "Forge Eval", 
                "UL Runtime",
                "Outcome",
            ],
        )

    def get_profile(self, profile_id: str) -> Optional[RuntimeProfile]:
        return self._profiles.get(profile_id)

    def register_profile(self, profile: RuntimeProfile) -> None:
        self._profiles[profile.profile_id] = profile

    def runtime_class_for_profile(self, profile_id: str) -> Optional[type]:
        """Factory method - returns runtime class for profile."""
        profile = self.get_profile(profile_id)
        if not profile:
            return None
        # In practice, would return actual runtime class
        return None


@dataclass
class ULRuntimeSubstrate:
    """Composite substrate with all constitutional primitives."""
    adapter_protocol: Any
    law_spine: LawSpine
    bootstrap_law: BootstrapLaw
    law_ledger: Any
    foundation_store: Any
    host_attestation: Any
    identity_registry: Any
    identity_verifier: Any
    law_context_builder: Any
    cisiv: Any
    mutation_gate: Any
    mutation_broker: Any
    verification_engine: Any

    def primitive_inventory(self) -> List[str]:
        """List all available primitives."""
        return [
            "adapter_protocol",
            "law_spine", 
            "bootstrap_law",
            "law_ledger",
            "foundation_store",
            "host_attestation",
            "identity_registry",
            "identity_verifier",
            "law_context_builder",
            "cisiv",
            "mutation_gate",
            "mutation_broker",
            "verification_engine",
        ]

    def status_payload(self) -> Dict[str, Any]:
        """Get status of all primitives."""
        return {
            "law_spine": self.law_spine.snapshot().__dict__,
            "bootstrap_law": {"ok": self.bootstrap_law.ok, "reason": self.bootstrap_law.reason},
            "primitives": self.primitive_inventory(),
        }


class ULDesktopRuntimeBootstrap:
    """Desktop runtime bootstrap: venv, deps, manifest, verification, PyInstaller."""
    
    def __init__(self, runtime_root: str):
        self._runtime_root = runtime_root
        self._manifest: Dict[str, Any] = {}

    def prepare(self, with_build_tools: bool = False) -> Dict[str, Any]:
        """Prepare runtime environment."""
        # This would create venv, install deps, etc.
        self._manifest = {
            "runtime_name": "ARIS V2 UL Desktop Runtime",
            "runtime_root": self._runtime_root,
            "venv_root": f"{self._runtime_root}/venv",
            "python_executable": f"{self._runtime_root}/venv/Scripts/python.exe",
            "identity_source": "UL",
            "governance_model": "CISIV",
            "binding_layer": "Universal Adapter Protocol",
            "speech_chain": ["0001", "1000", "1001"],
            "foundation_entries": [
                "ARIS_DOC_CHANNEL_LOCKED",
                "ARIS_HANDBOOK_LOCKED", 
                "UL_ROOT_LAW_LOCKED",
            ],
            "desktop_modules": [
                "PySide6.QtCore",
                "PySide6.QtGui", 
                "PySide6.QtWidgets",
                "uvicorn",
                "fastapi",
            ],
            "install_extras": ["desktop-build"],
            "launch_module": "evolving_ai.aris_runtime.desktop",
            "build_module": "evolving_ai.aris_runtime.desktop_build",
            "pyinstaller_artifact": "ARIS V2.exe",
            "profile_ids": ["v2"],
            "profile_artifacts": ["ARIS V2"],
            "model_router_mode": "auto",
            "model_systems": [
                "General: gemma3:12b",
                "Coding: devstral",
                "Light Coding: qwen2.5-coder:7b",
            ],
        }
        
        # Compute manifest hash
        content = json.dumps(self._manifest, sort_keys=True, separators=(",", ":"))
        self._manifest["manifest_hash"] = hashlib.sha256(content.encode("utf-8")).hexdigest()
        
        return self._manifest

    def verify(self) -> tuple[bool, List[str]]:
        """Verify imports and smokecheck."""
        errors = []
        # Would verify imports here
        return len(errors) == 0, errors

    def generate_build_command(self, variant: str = "v2", build_tag: str = "current") -> str:
        """Generate PyInstaller build command."""
        return f"py -3.12 -m evolving_ai.aris_runtime.desktop_build --variant {variant} --build-current"