from __future__ import annotations

from dataclasses import dataclass
import re
from typing import Any


STATE_ORDER = (
    "lost",
    "burdened",
    "seeking",
    "struggling",
    "awakening",
    "building",
    "transforming",
    "steady",
)

ARCHETYPE_LABELS = {
    "hero": "Hero",
    "shadow": "Shadow",
    "guide": "Guide",
    "builder": "Builder",
    "trickster": "Trickster",
    "witness": "Witness",
}

STATE_LABELS = {
    "lost": "Lost",
    "burdened": "Burdened",
    "seeking": "Seeking",
    "struggling": "Struggling",
    "awakening": "Awakening",
    "building": "Building",
    "transforming": "Transforming",
    "steady": "Steady",
}

STATE_HINTS = {
    "lost": ("lost", "stuck", "nothing is moving", "nothing works", "numb", "empty", "directionless"),
    "burdened": ("burdened", "guilt", "ashamed", "shame", "regret", "barely", "heavy", "weight"),
    "struggling": (
        "survive",
        "survival",
        "collapse",
        "overwhelmed",
        "exhausted",
        "burned out",
        "breaking",
        "fight just to",
    ),
    "awakening": ("awakening", "idea", "breakthrough", "vision", "change everything", "wake up", "clarity"),
    "building": ("build", "building", "system", "routine", "structure", "ship", "project", "discipline"),
    "transforming": ("transform", "transformation", "reaction", "control", "anger", "rage", "pause", "choose differently"),
    "steady": ("steady", "stable", "consistent", "holding the line", "maintain", "maintenance", "track one win"),
}

TRIGGER_TERMS = ("mystic", "mythic")
REQUEST_TERMS = ("reading", "archetype", "current state", "next move", "next action", "read me", "interpret")
PREFIX_PATTERNS = (
    "mystic reading",
    "mythic reading",
    "use mystic",
    "use mythic",
    "read me mythically",
    "read me mystically",
)


def humanize(value: str | None) -> str:
    key = value or ""
    if key in STATE_LABELS:
        return STATE_LABELS[key]
    if key in ARCHETYPE_LABELS:
        return ARCHETYPE_LABELS[key]
    return str(value or "").replace("_", " ").title()


@dataclass(slots=True)
class MysticReading:
    input_text: str
    state: str
    dominant_archetype: str
    opposing_archetype: str
    trial: str
    next_action: str
    meaning: str
    risk: str
    detected_signals: list[str]

    def to_dict(self) -> dict[str, Any]:
        return {
            "input_text": self.input_text,
            "state": self.state,
            "state_label": humanize(self.state),
            "dominant_archetype": self.dominant_archetype,
            "dominant_archetype_label": humanize(self.dominant_archetype),
            "opposing_archetype": self.opposing_archetype,
            "opposing_archetype_label": humanize(self.opposing_archetype),
            "trial": self.trial,
            "next_action": self.next_action,
            "meaning": self.meaning,
            "risk": self.risk,
            "detected_signals": list(self.detected_signals),
        }


def extract_mystic_prompt(text: str | None) -> str | None:
    cleaned = " ".join(str(text or "").split()).strip()
    if not cleaned:
        return None
    lower = cleaned.lower()
    if not any(term in lower for term in TRIGGER_TERMS):
        return None
    for prefix in PREFIX_PATTERNS:
        if lower.startswith(prefix):
            remainder = cleaned[len(prefix) :].lstrip(" :,-")
            return remainder or cleaned
    if any(term in lower for term in REQUEST_TERMS):
        stripped = re.sub(r"\b(mystic|mythic)\b", "", cleaned, flags=re.IGNORECASE)
        stripped = re.sub(r"\b(reading|interpretation)\b", "", stripped, flags=re.IGNORECASE)
        stripped = re.sub(
            r"^(give me|show me|offer me|run|use|do)\s+(a\s+|an\s+|the\s+)?",
            "",
            stripped,
            flags=re.IGNORECASE,
        )
        stripped = " ".join(stripped.split()).strip(" :,-")
        return stripped or cleaned
    return None
