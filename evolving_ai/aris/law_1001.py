from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
import hashlib
from typing import Any


LAW_1001_ID = "1001"
LAW_1001_TITLE = "1001 Meta Law"
LAW_1001_TEXT = (
    "All valid system behavior must begin under law, pass through non-bypassable "
    "validation, and only return if verified. No direct, hidden, or unverified path may exist."
)


def _utc_now() -> str:
    return datetime.now(UTC).isoformat()


def _text_hash(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


@dataclass(frozen=True, slots=True)
class Law1001Binding:
    context_kind: str
    context_id: str
    bound_at: str
    active: bool
    immutable: bool
    bound_under_law: bool
    non_bypassable_validation: bool
    verified_return_required: bool
    no_direct_path: bool
    no_hidden_path: bool

    def payload(self) -> dict[str, Any]:
        return {
            "context_kind": self.context_kind,
            "context_id": self.context_id,
            "bound_at": self.bound_at,
            "active": self.active,
            "immutable": self.immutable,
            "bound_under_law": self.bound_under_law,
            "non_bypassable_validation": self.non_bypassable_validation,
            "verified_return_required": self.verified_return_required,
            "no_direct_path": self.no_direct_path,
            "no_hidden_path": self.no_hidden_path,
        }


class MetaLaw1001:
    """Dedicated immutable startup and runtime binding for 1001."""

    def __init__(self) -> None:
        self._expected_hash = _text_hash(LAW_1001_TEXT)

    def validate(self) -> dict[str, Any]:
        active = bool(LAW_1001_ID == "1001" and LAW_1001_TEXT and _text_hash(LAW_1001_TEXT) == self._expected_hash)
        return {
            "id": LAW_1001_ID,
            "title": LAW_1001_TITLE,
            "text": LAW_1001_TEXT,
            "text_hash": self._expected_hash,
            "immutable": True,
            "protected_core": True,
            "required_before_startup": True,
            "active": active,
        }

    def bind(
        self,
        *,
        context_kind: str,
        context_id: str,
        bypass_requested: bool,
        direct_path_requested: bool,
        hidden_path_requested: bool,
    ) -> Law1001Binding:
        status = self.validate()
        active = bool(status["active"])
        return Law1001Binding(
            context_kind=str(context_kind or "runtime").strip() or "runtime",
            context_id=str(context_id or "system").strip() or "system",
            bound_at=_utc_now(),
            active=active,
            immutable=True,
            bound_under_law=active,
            non_bypassable_validation=not bool(bypass_requested),
            verified_return_required=True,
            no_direct_path=not bool(direct_path_requested),
            no_hidden_path=not bool(hidden_path_requested),
        )
