"""IdentityRegistry - Protected identities with lineage_required, copy_protected."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Set
import threading


@dataclass
class IdentityConfig:
    """Configuration for a protected identity."""
    name: str
    lineage_required: bool = True
    copy_protected: bool = True
    required_host_capabilities: List[str] = field(default_factory=list)
    allowed_scopes: List[str] = field(default_factory=lambda: ["*"])
    created_at: float = field(default_factory=lambda: __import__('time').time())


class IdentityRegistry:
    """Protected identities (ARIS, AAIS) with lineage_required, copy_protected."""
    
    DEFAULT_PROTECTED = {
        "ARIS": IdentityConfig(
            name="ARIS",
            lineage_required=True,
            copy_protected=True,
            required_host_capabilities=["governance", "runtime", "audit"],
            allowed_scopes=["*"],
        ),
        "AAIS": IdentityConfig(
            name="AAIS",
            lineage_required=True,
            copy_protected=True,
            required_host_capabilities=["governance", "audit"],
            allowed_scopes=["*"],
        ),
    }

    def __init__(self):
        self._identities: Dict[str, IdentityConfig] = {}
        self._lock = threading.RLock()
        
        # Register default protected identities
        for name, config in self.DEFAULT_PROTECTED.items():
            self._identities[name] = config

    def register(self, config: IdentityConfig) -> bool:
        """Register a new identity."""
        with self._lock:
            if config.name in self._identities:
                return False
            self._identities[config.name] = config
            return True

    def get(self, name: str) -> Optional[IdentityConfig]:
        with self._lock:
            return self._identities.get(name)

    def is_protected(self, name: str) -> bool:
        with self._lock:
            return name in self._identities

    def get_protected_identities(self) -> List[str]:
        with self._lock:
            return list(self._identities.keys())

    def validate_host_capabilities(self, identity: str, host_capabilities: List[str]) -> bool:
        """Check if host has required capabilities for identity."""
        with self._lock:
            config = self._identities.get(identity)
            if not config:
                return False
            
            host_caps = set(host_capabilities)
            required = set(config.required_host_capabilities)
            return required.issubset(host_caps)

    def get_allowed_scopes(self, identity: str) -> List[str]:
        with self._lock:
            config = self._identities.get(identity)
            return config.allowed_scopes if config else []

    def requires_lineage(self, identity: str) -> bool:
        with self._lock:
            config = self._identities.get(identity)
            return config.lineage_required if config else False

    def is_copy_protected(self, identity: str) -> bool:
        with self._lock:
            config = self._identities.get(identity)
            return config.copy_protected if config else False