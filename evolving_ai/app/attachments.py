from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class Attachment:
    name: str
    mime_type: str
    content: str
    kind: str

    @property
    def is_text(self) -> bool:
        return self.kind == "text"

    @property
    def is_image(self) -> bool:
        return self.kind == "image"

    def compact_preview(self) -> str:
        if self.is_image:
            return f"{self.name} ({self.mime_type}, image attachment)"
        compact = " ".join(self.content.split())
        return f"{self.name}: {compact[:220]}"
