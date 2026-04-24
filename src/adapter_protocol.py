from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Iterable


@dataclass(frozen=True, slots=True)
class HostDeclaration:
    name: str
    version: str
    capabilities: tuple[str, ...] = field(default_factory=tuple)
    legitimacy_token: str = ""
    session_binding: str = ""
    host_class: str = "internal"


@dataclass(frozen=True, slots=True)
class AdapterBindingResult:
    allowed: bool
    reason: str
    identity_preserving: bool
    declared_capabilities: tuple[str, ...]
    required_capabilities: tuple[str, ...]
    missing_capabilities: tuple[str, ...]
    host_class: str

    def payload(self) -> dict[str, Any]:
        return {
            "allowed": self.allowed,
            "reason": self.reason,
            "identity_preserving": self.identity_preserving,
            "declared_capabilities": list(self.declared_capabilities),
            "required_capabilities": list(self.required_capabilities),
            "missing_capabilities": list(self.missing_capabilities),
            "host_class": self.host_class,
        }


class AdapterProtocol:
    def normalize_capabilities(self, capabilities: Iterable[str] | None) -> tuple[str, ...]:
        normalized = {
            str(capability or "").strip().lower()
            for capability in list(capabilities or ())
            if str(capability or "").strip()
        }
        return tuple(sorted(normalized))

    def validate(self, declaration: HostDeclaration) -> tuple[bool, str]:
        if not declaration.name or not declaration.version:
            return False, "Host declaration is incomplete."
        if not declaration.capabilities:
            return False, "Host declaration capabilities are missing."
        if not declaration.legitimacy_token:
            return False, "Host declaration legitimacy token is missing."
        return True, "Host declaration is structurally valid."

    def evaluate_identity_binding(
        self,
        declaration: HostDeclaration,
        *,
        required_capabilities: Iterable[str] | None = None,
        protected: bool = False,
    ) -> AdapterBindingResult:
        ok, reason = self.validate(declaration)
        declared = self.normalize_capabilities(declaration.capabilities)
        required = self.normalize_capabilities(required_capabilities)
        missing = tuple(capability for capability in required if capability not in declared)
        identity_preserving = not missing
        if not ok:
            return AdapterBindingResult(
                allowed=False,
                reason=reason,
                identity_preserving=False,
                declared_capabilities=declared,
                required_capabilities=required,
                missing_capabilities=missing,
                host_class=declaration.host_class,
            )
        if protected and missing:
            return AdapterBindingResult(
                allowed=False,
                reason=(
                    "Host cannot satisfy identity-preserving requirements for the protected identity claim."
                ),
                identity_preserving=False,
                declared_capabilities=declared,
                required_capabilities=required,
                missing_capabilities=missing,
                host_class=declaration.host_class,
            )
        return AdapterBindingResult(
            allowed=True,
            reason="Host declaration satisfies the Universal Adapter Protocol binding.",
            identity_preserving=identity_preserving,
            declared_capabilities=declared,
            required_capabilities=required,
            missing_capabilities=missing,
            host_class=declaration.host_class,
        )
