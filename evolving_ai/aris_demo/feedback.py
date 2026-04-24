from __future__ import annotations

from datetime import datetime, timezone
import json
import os
from pathlib import Path
from typing import Any


_ALLOWED_FEEDBACK_TYPES = {
    "bug",
    "confusing",
    "impressive",
    "feature_request",
}


def _utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def _slug(value: str) -> str:
    normalized = "".join(ch.lower() if ch.isalnum() else "-" for ch in str(value or "").strip())
    collapsed = "-".join(part for part in normalized.split("-") if part)
    return collapsed or "feedback"


def feedback_form_url() -> str:
    return str(os.getenv("ARIS_FEEDBACK_FORM_URL", "")).strip()


def build_feedback_packet(
    *,
    app_version: str,
    feedback_type: str,
    user_note: str,
    active_brain: str,
    active_tier: str,
    active_workspace: str,
    recent_events: list[dict[str, Any]],
    recent_logs: list[dict[str, Any]],
    runtime_profile: str,
) -> dict[str, Any]:
    normalized_type = str(feedback_type or "").strip().lower().replace(" ", "_")
    if normalized_type not in _ALLOWED_FEEDBACK_TYPES:
        raise ValueError(f"Unsupported feedback type: {feedback_type}")
    note = str(user_note or "").strip()
    return {
        "feedback_type": normalized_type,
        "app_version": str(app_version or "ARIS Demo").strip() or "ARIS Demo",
        "runtime_profile": str(runtime_profile or "demo").strip() or "demo",
        "active_brain": str(active_brain or "Inspect").strip() or "Inspect",
        "active_tier": str(active_tier or "Read Only").strip() or "Read Only",
        "active_workspace": str(active_workspace or "No workspace").strip() or "No workspace",
        "timestamp": _utc_now(),
        "recent_events": list(recent_events or [])[:20],
        "recent_logs": list(recent_logs or [])[:20],
        "user_note": note,
    }


def write_feedback_packet(feedback_dir: Path, packet: dict[str, Any]) -> Path:
    feedback_dir.mkdir(parents=True, exist_ok=True)
    timestamp = str(packet.get("timestamp", _utc_now())).replace(":", "-")
    feedback_type = _slug(str(packet.get("feedback_type", "feedback")))
    target_path = feedback_dir / f"{timestamp}-{feedback_type}.json"
    target_path.write_text(json.dumps(packet, indent=2), encoding="utf-8")
    return target_path.resolve()
