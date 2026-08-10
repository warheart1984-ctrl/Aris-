"""Adapters - UniversalAdapterProtocol, HostAttestation, IdentityVerifier, LawContextBuilder."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional
from jon_core.contexts import HostDeclaration, AdapterBindingResult, RuntimeLawContext


@dataclass
class UniversalAdapterProtocol:
    """Host declaration normalization, validation, identity binding evaluation."""
    
    def normalize_capabilities(self, capabilities: List[str]) -> List[str]:
        """Normalize capability strings."""
        normalized = []
        for cap in capabilities:
            cap = cap.strip().lower().replace(" ", "_")
            if cap and cap not in normalized:
                normalized.append(cap)
        return normalized

    def validate(self, declaration: HostDeclaration) -> AdapterBindingResult:
        """Validate host declaration and evaluate capability matching."""
        normalized_caps = self.normalize_capabilities(declaration.capabilities)
        
        # Required capabilities based on host_class
        required = self._get_required_capabilities(declaration.host_class)
        
        missing = [c for c in required if c not in normalized_caps]
        allowed = len(missing) == 0
        
        # Identity binding evaluation
        identity_preserving = self._evaluate_identity_binding(declaration)
        
        return AdapterBindingResult(
            allowed=allowed,
            reason="All capabilities satisfied" if allowed else f"Missing capabilities: {missing}",
            identity_preserving=identity_preserving,
            declared_capabilities=normalized_caps,
            required_capabilities=required,
            missing_capabilities=missing,
            host_class=declaration.host_class,
        )

    def _get_required_capabilities(self, host_class: str) -> List[str]:
        """Get required capabilities for host class."""
        requirements = {
            "operator": ["governance", "audit", "control"],
            "runtime": ["execution", "monitoring", "health"],
            "agent": ["execution", "memory", "communication"],
            "service": ["api", "persistence", "observability"],
        }
        return requirements.get(host_class, [])

    def _evaluate_identity_binding(self, declaration: HostDeclaration) -> bool:
        """Evaluate if host preserves identity."""
        # Check for protected identity capabilities
        protected_caps = {"governance", "audit", "identity"}
        declared = set(declaration.capabilities)
        return protected_caps.issubset(declared)


class HostAttestationService:
    """Host attestation and internal host building."""
    
    def __init__(self):
        self._internal_hosts: Dict[str, HostDeclaration] = {}
        self._legitimacy_tokens: Dict[str, str] = {}

    def verify(self, declaration: HostDeclaration) -> tuple[bool, str]:
        """Verify host declaration."""
        # Check legitimacy token
        if declaration.legitimacy_token not in self._legitimacy_tokens.values():
            return False, "Invalid legitimacy token"
        
        # Check session binding
        if not declaration.session_binding:
            return False, "Missing session binding"
        
        return True, "Host attested"

    def build_internal_host(
        self,
        name: str,
        version: str,
        capabilities: List[str],
        session_binding: str,
        host_class: str = "runtime",
    ) -> HostDeclaration:
        """Build internal host declaration."""
        import hashlib
        import time
        
        legitimacy_token = hashlib.sha256(
            f"{name}:{version}:{session_binding}:{time.time()}".encode()
        ).hexdigest()[:32]
        
        declaration = HostDeclaration(
            name=name,
            version=version,
            capabilities=capabilities,
            legitimacy_token=legitimacy_token,
            session_binding=session_binding,
            host_class=host_class,
        )
        
        self._internal_hosts[name] = declaration
        self._legitimacy_tokens[name] = legitimacy_token
        
        return declaration

    def get_legitimacy_token(self, host_name: str) -> Optional[str]:
        return self._legitimacy_tokens.get(host_name)


class IdentityVerifierService:
    """Identity verification with registry lookup."""
    
    def __init__(self, identity_registry):
        self._registry = identity_registry

    def verify(
        self,
        actor: str,
        requested_identity: str,
        host_attested: bool,
        lineage: str,
        adapter_binding: AdapterBindingResult,
    ) -> Dict[str, Any]:
        """Verify actor identity."""
        # Check registry
        config = self._registry.get(requested_identity)
        if not config:
            return {
                "legitimate": False,
                "name": requested_identity,
                "allowed_scopes": [],
                "identity_source": "unknown",
                "copy_protected": False,
                "lineage_required": False,
                "reason": "Identity not registered",
            }
        
        # Verify host attestation
        if not host_attested:
            return {
                "legitimate": False,
                "name": requested_identity,
                "allowed_scopes": [],
                "identity_source": "registry",
                "copy_protected": config.copy_protected,
                "lineage_required": config.lineage_required,
                "reason": "Host not attested",
            }
        
        # Verify adapter binding
        if not adapter_binding.allowed:
            return {
                "legitimate": False,
                "name": requested_identity,
                "allowed_scopes": [],
                "identity_source": "registry",
                "copy_protected": config.copy_protected,
                "lineage_required": config.lineage_required,
                "reason": f"Adapter binding failed: {adapter_binding.reason}",
            }
        
        # Verify identity preservation
        if not adapter_binding.identity_preserving and config.copy_protected:
            return {
                "legitimate": False,
                "name": requested_identity,
                "allowed_scopes": [],
                "identity_source": "registry",
                "copy_protected": config.copy_protected,
                "lineage_required": config.lineage_required,
                "reason": "Identity not preserved by adapter",
            }
        
        return {
            "legitimate": True,
            "name": requested_identity,
            "allowed_scopes": config.allowed_scopes,
            "identity_source": "registry",
            "copy_protected": config.copy_protected,
            "lineage_required": config.lineage_required,
            "reason": "Identity verified",
        }


class LawContextBuilder:
    """Build RuntimeLawContext from action, actor, route, host, etc."""
    
    def build_action_context(
        self,
        action: Dict[str, Any],
        actor: str,
        route_name: str,
        host: HostDeclaration,
        repo_changed: bool,
        protected_target: bool,
    ) -> RuntimeLawContext:
        """Build law context for action."""
        import hashlib
        import json
        
        # Derive lineage
        lineage_content = f"{actor}:{route_name}:{host.name}:{json.dumps(action, sort_keys=True)}"
        lineage = hashlib.sha256(lineage_content.encode("utf-8")).hexdigest()
        
        # Check forbidden caller fields
        forbidden_fields = {"identity", "scope", "speech", "host", "verification", "lineage"}
        caller_claims = {}
        for key, value in action.items():
            if key in forbidden_fields:
                # This would be a violation
                pass
            else:
                caller_claims[key] = value
        
        return RuntimeLawContext(
            identity=actor,
            scope=route_name,
            speech="0001",  # Default to intent declaration
            host=host.name,
            verification={
                "host_attested": True,
                "adapter_binding": host.host_class,
                "lineage": lineage,
            },
            action=action,
            caller_claims=caller_claims,
        )