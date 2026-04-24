from __future__ import annotations

from dataclasses import dataclass

from .adapter_protocol import AdapterBindingResult
from .identity_registry import IdentityRegistry


@dataclass(frozen=True, slots=True)
class VerifiedIdentity:
    name: str
    actor_class: str
    protected: bool
    legitimate: bool
    allowed_scopes: frozenset[str]
    identity_source: str
    copy_protected: bool
    lineage_required: bool
    required_host_capabilities: frozenset[str]
    reason: str


class IdentityVerifier:
    def __init__(self, registry: IdentityRegistry | None = None) -> None:
        self.registry = registry or IdentityRegistry()

    def verify(
        self,
        *,
        actor: str,
        requested_identity: str | None,
        host_attested: bool,
        lineage: str | None = None,
        adapter_binding: AdapterBindingResult | None = None,
    ) -> VerifiedIdentity:
        actor_name = str(actor or "external_user").strip() or "external_user"
        record = self.registry.get(actor_name)
        claimed = str(requested_identity or "").strip()
        claimed_record = self.registry.get(claimed) if claimed else record
        if claimed and self.registry.is_protected(claimed) and claimed != record.name:
            return VerifiedIdentity(
                name=claimed,
                actor_class=actor_name,
                protected=True,
                legitimate=False,
                allowed_scopes=frozenset(),
                identity_source=claimed_record.identity_source,
                copy_protected=True,
                lineage_required=True,
                required_host_capabilities=claimed_record.required_host_capabilities,
                reason="Protected identity claim did not match the trusted runtime actor.",
            )
        target = self.registry.get(claimed or actor_name)
        if target.copy_protected and not str(lineage or "").strip():
            return VerifiedIdentity(
                name=target.name,
                actor_class=actor_name,
                protected=True,
                legitimate=False,
                allowed_scopes=frozenset(),
                identity_source=target.identity_source,
                copy_protected=target.copy_protected,
                lineage_required=target.lineage_required,
                required_host_capabilities=target.required_host_capabilities,
                reason="Protected identity claim requires lineage.",
            )
        if target.protected and not host_attested:
            return VerifiedIdentity(
                name=target.name,
                actor_class=actor_name,
                protected=True,
                legitimate=False,
                allowed_scopes=frozenset(),
                identity_source=target.identity_source,
                copy_protected=target.copy_protected,
                lineage_required=target.lineage_required,
                required_host_capabilities=target.required_host_capabilities,
                reason="Protected identity could not be bound to an attested host.",
            )
        if target.protected and adapter_binding is not None and not adapter_binding.allowed:
            return VerifiedIdentity(
                name=target.name,
                actor_class=actor_name,
                protected=True,
                legitimate=False,
                allowed_scopes=frozenset(),
                identity_source=target.identity_source,
                copy_protected=target.copy_protected,
                lineage_required=target.lineage_required,
                required_host_capabilities=target.required_host_capabilities,
                reason=adapter_binding.reason,
            )
        return VerifiedIdentity(
            name=target.name,
            actor_class=actor_name,
            protected=target.protected,
            legitimate=(
                (host_attested and (adapter_binding.allowed if adapter_binding is not None else True))
                or not target.protected
            ),
            allowed_scopes=target.allowed_scopes,
            identity_source=target.identity_source,
            copy_protected=target.copy_protected,
            lineage_required=target.lineage_required,
            required_host_capabilities=target.required_host_capabilities,
            reason="Identity verified from trusted runtime sources."
            if (host_attested and (adapter_binding.allowed if adapter_binding is not None else True))
            or not target.protected
            else "Identity verification failed.",
        )
