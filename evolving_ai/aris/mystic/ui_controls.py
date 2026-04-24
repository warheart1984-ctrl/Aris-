from __future__ import annotations

from typing import Any


def build_mystic_ui_controls(payload: dict[str, Any]) -> list[dict[str, Any]]:
    active = bool(payload.get("active", False))
    muted = bool(payload.get("muted", False))
    if not active:
        return []
    return [
        {
            "id": "tick",
            "label": "Check In",
            "method": "POST",
            "endpoint": "/api/aris/mystic/tick",
            "enabled": True,
        },
        {
            "id": "break",
            "label": "I Took a Break",
            "method": "POST",
            "endpoint": "/api/aris/mystic/break",
            "enabled": True,
        },
        {
            "id": "acknowledge",
            "label": "Acknowledge",
            "method": "POST",
            "endpoint": "/api/aris/mystic/acknowledge",
            "enabled": True,
        },
        {
            "id": "mute_10m",
            "label": "Mute 10m",
            "method": "POST",
            "endpoint": "/api/aris/mystic/mute",
            "payload": {"minutes": 10},
            "enabled": not muted,
        },
    ]
