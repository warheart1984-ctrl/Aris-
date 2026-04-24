from __future__ import annotations

from dataclasses import dataclass
import hashlib
import json
from typing import Any
import uuid

from .adapter_protocol import HostDeclaration
from .constants_runtime import FORBIDDEN_CALLER_FIELDS, SCOPE_BY_ACTION_TYPE
from .host_attestation import HostAttestation
from .identity_verifier import IdentityVerifier


@dataclass(frozen=True, slots=True)
class RuntimeLawContext:
    request_id: str
    actor: str
    claimed_identity: str
    lineage: str
    legitimacy_token: str
    requested_scope: str
    allowed_scopes: frozenset[str]
    state_present: bool
    code_present: bool
    verification_present: bool
    route_name: str
    target: str
    session_id: str
    host_name: str
    host_version: str
    host_attested: bool
    identity_verified: bool
    repo_changed: bool
    protected_target: bool
    action_type: str
    caller_claims: tuple[str, ...]
    declared_lineage: str = ""
    derived_lineage: str = ""
    host_capabilities: tuple[str, ...] = ()
    identity_source: str = ""
    copy_protected: bool = False
    lineage_required: bool = False
    adapter_binding_ok: bool = True
    adapter_binding_reason: str = ""
    identity_preserving_host: bool = False

    def payload(self) -> dict[str, Any]:
        return {
            "request_id": self.request_id,
            "actor": self.actor,
            "claimed_identity": self.claimed_identity,
            "lineage": self.lineage,
            "declared_lineage": self.declared_lineage,
            "derived_lineage": self.derived_lineage,
            "legitimacy_token": self.legitimacy_token,
            "requested_scope": self.requested_scope,
            "allowed_scopes": sorted(self.allowed_scopes),
            "state_present": self.state_present,
            "code_present": self.code_present,
            "verification_present": self.verification_present,
            "route_name": self.route_name,
            "target": self.target,
            "session_id": self.session_id,
            "host_name": self.host_name,
            "host_version": self.host_version,
            "host_capabilities": list(self.host_capabilities),
            "host_attested": self.host_attested,
            "identity_verified": self.identity_verified,
            "identity_source": self.identity_source,
            "copy_protected": self.copy_protected,
            "lineage_required": self.lineage_required,
            "adapter_binding_ok": self.adapter_binding_ok,
            "adapter_binding_reason": self.adapter_binding_reason,
            "identity_preserving_host": self.identity_preserving_host,
            "repo_changed": self.repo_changed,
            "protected_target": self.protected_target,
            "action_type": self.action_type,
            "caller_claims": list(self.caller_claims),
        }


class LawContextBuilder:
    def __init__(
        self,
        *,
        host_attestation: HostAttestation | None = None,
        identity_verifier: IdentityVerifier | None = None,
    ) -> None:
        self.host_attestation = host_attestation or HostAttestation()
        self.identity_verifier = identity_verifier or IdentityVerifier()

    def _claimed_field_present(self, action: dict[str, Any], field: str) -> bool:
        if field not in action:
            return False
        value = action.get(field)
        if isinstance(value, bool):
            return value
        if value is None:
            return False
        if isinstance(value, (list, tuple, set, dict)):
            return bool(value)
        return bool(str(value).strip())

    def build_action_context(
        self,
        action: dict[str, Any],
        *,
        actor: str,
        route_name: str,
        host: HostDeclaration,
        repo_changed: bool,
        protected_target: bool,
    ) -> RuntimeLawContext:
        requested_scope = SCOPE_BY_ACTION_TYPE.get(
            str(action.get("action_type") or "").strip(),
            "read",
        )
        host_attested, _ = self.host_attestation.verify(host)
        declared_lineage = str(action.get("lineage") or "").strip()
        requested_identity = str(action.get("claimed_identity") or "").strip() or None
        target_record = self.identity_verifier.registry.get(requested_identity or actor)
        adapter_binding = self.host_attestation.protocol.evaluate_identity_binding(
            host,
            required_capabilities=target_record.required_host_capabilities,
            protected=target_record.protected,
        )
        identity = self.identity_verifier.verify(
            actor=actor,
            requested_identity=requested_identity,
            host_attested=host_attested,
            lineage=declared_lineage,
            adapter_binding=adapter_binding,
        )
        target = str(action.get("target") or "").strip()
        material = {
            "action_type": str(action.get("action_type") or "").strip(),
            "session_id": str(action.get("session_id") or "").strip(),
            "purpose": str(action.get("purpose") or "").strip(),
            "target": target,
            "patch": str(action.get("patch") or ""),
            "code": str(action.get("code") or ""),
            "command": list(action.get("command") or []),
        }
        lineage = hashlib.sha256(
            json.dumps(material, sort_keys=True).encode("utf-8")
        ).hexdigest()
        caller_claims = tuple(
            field
            for field in FORBIDDEN_CALLER_FIELDS
            if self._claimed_field_present(action, field)
        )
        resolved_lineage = declared_lineage or lineage
        return RuntimeLawContext(
            request_id=str(action.get("action_id") or f"law_{uuid.uuid4().hex[:12]}"),
            actor=actor,
            claimed_identity=identity.name,
            lineage=resolved_lineage,
            declared_lineage=declared_lineage,
            derived_lineage=lineage,
            legitimacy_token=host.legitimacy_token,
            requested_scope=requested_scope,
            allowed_scopes=identity.allowed_scopes,
            state_present=bool(material["action_type"] and material["purpose"]),
            code_present=bool(material["patch"] or material["code"] or material["command"]),
            verification_present=False,
            route_name=route_name,
            target=target,
            session_id=str(action.get("session_id") or "").strip() or "system",
            host_name=host.name,
            host_version=host.version,
            host_capabilities=adapter_binding.declared_capabilities,
            host_attested=host_attested,
            identity_verified=identity.legitimate,
            identity_source=identity.identity_source,
            copy_protected=identity.copy_protected,
            lineage_required=identity.lineage_required,
            adapter_binding_ok=adapter_binding.allowed,
            adapter_binding_reason=adapter_binding.reason,
            identity_preserving_host=adapter_binding.identity_preserving,
            repo_changed=repo_changed,
            protected_target=protected_target,
            action_type=material["action_type"],
            caller_claims=caller_claims,
        )
