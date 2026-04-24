from __future__ import annotations

import hashlib
import hmac
import os

from .adapter_protocol import AdapterProtocol, HostDeclaration
from .constants_runtime import HOST_LEGITIMACY_SECRET_ENV, KNOWN_INTERNAL_HOSTS


def _secret() -> bytes:
    return os.getenv(HOST_LEGITIMACY_SECRET_ENV, "aris-local-dev-secret").encode("utf-8")


class HostAttestation:
    def __init__(self, protocol: AdapterProtocol | None = None) -> None:
        self.protocol = protocol or AdapterProtocol()

    def issue_token(self, *, name: str, version: str, session_binding: str) -> str:
        message = f"{name}:{version}:{session_binding}".encode("utf-8")
        return hmac.new(_secret(), message, hashlib.sha256).hexdigest()

    def build_internal_host(
        self,
        *,
        name: str,
        version: str,
        capabilities: tuple[str, ...],
        session_binding: str,
    ) -> HostDeclaration:
        return HostDeclaration(
            name=name,
            version=version,
            capabilities=self.protocol.normalize_capabilities(capabilities),
            legitimacy_token=self.issue_token(
                name=name,
                version=version,
                session_binding=session_binding,
            ),
            session_binding=session_binding,
            host_class="internal",
        )

    def verify(self, declaration: HostDeclaration) -> tuple[bool, str]:
        ok, reason = self.protocol.validate(declaration)
        if not ok:
            return False, reason
        if declaration.host_class == "internal" and declaration.name not in KNOWN_INTERNAL_HOSTS:
            return False, "Host is not in the trusted internal registry."
        expected = self.issue_token(
            name=declaration.name,
            version=declaration.version,
            session_binding=declaration.session_binding,
        )
        if not hmac.compare_digest(expected, declaration.legitimacy_token):
            return False, "Host legitimacy token failed attestation."
        return True, "Host attestation verified."
