"""Λ.4 IdentityBoundaryEnforcer - Isolate agent execution contexts."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, Set, Optional
import threading
import uuid


@dataclass
class IdentityContext:
    """Isolated execution context for an agent."""
    identity: str
    memory_namespace: Dict[str, Any] = field(default_factory=dict)
    config_namespace: Dict[str, Any] = field(default_factory=dict)
    audit_stream: list = field(default_factory=list)
    parent_identity: Optional[str] = None
    created_at: float = field(default_factory=lambda: __import__('time').time())


class IdentityBoundaryEnforcer:
    """Enforces isolation between agent execution contexts."""
    
    def __init__(self):
        self._contexts: Dict[str, IdentityContext] = {}
        self._lock = threading.RLock()
        self._protected_identities: Set[str] = {"ARIS", "AAIS"}

    def create_context(self, identity: str, parent: Optional[str] = None) -> IdentityContext:
        """Create a new isolated context."""
        if identity in self._protected_identities and parent is not None:
            raise ValueError(f"Protected identity '{identity}' cannot have parent")
        
        with self._lock:
            if identity in self._contexts:
                raise ValueError(f"Context for '{identity}' already exists")
            
            ctx = IdentityContext(identity=identity, parent_identity=parent)
            self._contexts[identity] = ctx
            return ctx

    def get_context(self, identity: str) -> Optional[IdentityContext]:
        """Get existing context."""
        with self._lock:
            return self._contexts.get(identity)

    def destroy_context(self, identity: str) -> bool:
        """Destroy a context."""
        with self._lock:
            if identity in self._protected_identities:
                raise ValueError(f"Cannot destroy protected identity '{identity}'")
            return self._contexts.pop(identity, None) is not None

    def set_memory(self, identity: str, key: str, value: Any) -> None:
        """Set memory in isolated namespace."""
        ctx = self.get_context(identity)
        if ctx is None:
            raise ValueError(f"No context for '{identity}'")
        ctx.memory_namespace[key] = value

    def get_memory(self, identity: str, key: str, default: Any = None) -> Any:
        """Get memory from isolated namespace."""
        ctx = self.get_context(identity)
        if ctx is None:
            return default
        return ctx.memory_namespace.get(key, default)

    def set_config(self, identity: str, key: str, value: Any) -> None:
        """Set config in isolated namespace."""
        ctx = self.get_context(identity)
        if ctx is None:
            raise ValueError(f"No context for '{identity}'")
        ctx.config_namespace[key] = value

    def get_config(self, identity: str, key: str, default: Any = None) -> Any:
        """Get config from isolated namespace."""
        ctx = self.get_context(identity)
        if ctx is None:
            return default
        return ctx.config_namespace.get(key, default)

    def emit_audit(self, identity: str, event: Dict[str, Any]) -> None:
        """Emit audit event to identity's stream."""
        ctx = self.get_context(identity)
        if ctx is None:
            raise ValueError(f"No context for '{identity}'")
        ctx.audit_stream.append(event)

    def get_audit_stream(self, identity: str) -> list:
        """Get audit stream for identity."""
        ctx = self.get_context(identity)
        if ctx is None:
            return []
        return list(ctx.audit_stream)

    def list_identities(self) -> list[str]:
        """List all active identities."""
        with self._lock:
            return list(self._contexts.keys())

    def is_protected(self, identity: str) -> bool:
        """Check if identity is protected."""
        return identity in self._protected_identities


class IdentityLeakDetector:
    """Background process checking for cross-agent references."""
    
    def __init__(self, enforcer: IdentityBoundaryEnforcer):
        self.enforcer = enforcer
        self._leaks: list[Dict[str, Any]] = []
        self._lock = threading.RLock()

    def scan_for_leaks(self) -> list[Dict[str, Any]]:
        """Scan all contexts for cross-references."""
        leaks = []
        with self._lock:
            identities = self.enforcer.list_identities()
            
            for identity in identities:
                ctx = self.enforcer.get_context(identity)
                if ctx is None:
                    continue
                
                # Check memory namespace for references to other identities
                for key, value in ctx.memory_namespace.items():
                    if isinstance(value, str) and value in identities and value != identity:
                        leaks.append({
                            "source_identity": identity,
                            "target_identity": value,
                            "key": key,
                            "type": "memory_reference",
                            "detected_at": __import__('time').time(),
                        })
                
                # Check config namespace
                for key, value in ctx.config_namespace.items():
                    if isinstance(value, str) and value in identities and value != identity:
                        leaks.append({
                            "source_identity": identity,
                            "target_identity": value,
                            "key": key,
                            "type": "config_reference",
                            "detected_at": __import__('time').time(),
                        })
                
                # Check audit stream
                for event in ctx.audit_stream:
                    if isinstance(event, dict):
                        actor = event.get("actor") or event.get("identity")
                        if actor and actor in identities and actor != identity:
                            leaks.append({
                                "source_identity": identity,
                                "target_identity": actor,
                                "event": event,
                                "type": "audit_reference",
                                "detected_at": __import__('time').time(),
                            })
            
            self._leaks = leaks
            return leaks

    def get_leaks(self) -> list[Dict[str, Any]]:
        with self._lock:
            return list(self._leaks)