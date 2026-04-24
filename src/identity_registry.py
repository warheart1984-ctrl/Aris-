from __future__ import annotations

from dataclasses import dataclass, field

from .constants_runtime import (
    IDENTITY_PRESERVING_CAPABILITIES,
    PROTECTED_IDENTITIES,
    UL_IDENTITY_SOURCE,
)


@dataclass(frozen=True, slots=True)
class IdentityRecord:
    name: str
    protected: bool
    allowed_scopes: frozenset[str]
    identity_source: str = UL_IDENTITY_SOURCE
    lineage_required: bool = False
    copy_protected: bool = False
    required_host_capabilities: frozenset[str] = field(default_factory=frozenset)


class IdentityRegistry:
    def __init__(self) -> None:
        self._records = {
            "ARIS": IdentityRecord(
                name="ARIS",
                protected=True,
                allowed_scopes=frozenset(
                    {"read", "chat", "workspace_mutation", "execution", "approval", "identity", "admin"}
                ),
                lineage_required=True,
                copy_protected=True,
                required_host_capabilities=IDENTITY_PRESERVING_CAPABILITIES,
            ),
            "AAIS": IdentityRecord(
                name="AAIS",
                protected=True,
                allowed_scopes=frozenset(
                    {"read", "chat", "workspace_mutation", "execution", "approval", "identity", "admin"}
                ),
                lineage_required=True,
                copy_protected=True,
                required_host_capabilities=IDENTITY_PRESERVING_CAPABILITIES,
            ),
            "forge": IdentityRecord(
                name="forge",
                protected=False,
                allowed_scopes=frozenset({"proposal", "planning"}),
            ),
            "forge_eval": IdentityRecord(
                name="forge_eval",
                protected=False,
                allowed_scopes=frozenset({"verification"}),
            ),
            "mystic": IdentityRecord(
                name="mystic",
                protected=False,
                allowed_scopes=frozenset({"read", "reflection", "sustainment"}),
            ),
            "api": IdentityRecord(
                name="api",
                protected=False,
                allowed_scopes=frozenset(
                    {"read", "chat", "workspace_mutation", "execution", "approval", "introspection"}
                ),
            ),
            "external_user": IdentityRecord(
                name="external_user",
                protected=False,
                allowed_scopes=frozenset({"read", "chat"}),
            ),
        }

    def get(self, name: str) -> IdentityRecord:
        return self._records.get(
            str(name or "").strip(),
            self._records["api"],
        )

    def is_protected(self, name: str) -> bool:
        return str(name or "").strip() in PROTECTED_IDENTITIES
