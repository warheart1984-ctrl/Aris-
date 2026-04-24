"""Helpers for keeping Forge output bounded and predictable."""

from __future__ import annotations

from typing import Iterable

from forge.schemas import TraceEvent


ABSOLUTE_MAX_OUTPUT_CHARS = 50_000
MAX_TRACE_EVENTS = 8
MAX_TRACE_DATA_CHARS = 180


def clamp_output_chars(value: object, default: int = 20_000) -> int:
    """Clamp a requested output size into a safe range."""

    try:
        number = int(value)
    except (TypeError, ValueError):
        number = int(default)
    return max(1000, min(ABSOLUTE_MAX_OUTPUT_CHARS, number))


def bound_text(text: object, max_chars: int = 20_000) -> str:
    """Clamp any text payload to the configured character budget."""

    payload = str(text or "")
    return payload[:max_chars] if len(payload) > max_chars else payload


def bound_trace_events(events: Iterable[TraceEvent]) -> list[TraceEvent]:
    """Return a small, safe trace payload."""

    bounded: list[TraceEvent] = []
    for event in list(events)[:MAX_TRACE_EVENTS]:
        bounded.append(
            TraceEvent(
                event=str(event.event or "")[:48],
                data=bound_text(event.data, MAX_TRACE_DATA_CHARS),
            )
        )
    return bounded
