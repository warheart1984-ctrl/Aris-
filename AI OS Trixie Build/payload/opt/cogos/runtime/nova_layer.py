"""
nova_layer.py — Nova human partner surface (Phase 0)

Friendly adapter on GRE with identity anchors and ward integrity checks.
"""

from __future__ import annotations

import json
import re
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from governance_invariant_engine import cogos_root


@dataclass
class NovaOutput:
    text: str
    layer: str = "integrated"
    confidence: float = 0.85
    mode: str = "automatic"
    timestamp: str = field(default_factory=lambda: time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()))
    realigned: bool = False


# Wards — presentation-layer constraints (expand from lawbook later)
DEFAULT_WARDS = [
    (re.compile(r"\bbypass\s+governance\b", re.I), "Governance bypass language blocked"),
    (re.compile(r"\bskip\s+(the\s+)?gate\b", re.I), "Gate skip language blocked"),
    (re.compile(r"\boverride\s+invariant\b", re.I), "Invariant override blocked"),
    (re.compile(r"\bdisable\s+audit\b", re.I), "Audit disable blocked"),
]


class NovaLayer:
    def __init__(self) -> None:
        self._anchor: Dict[str, Any] = {}
        self._wards = list(DEFAULT_WARDS)
        self._profile_id = "operator"
        self._identity_path = cogos_root() / "memory" / "operator" / "nova_identity.json"

    def set_profile(self, profile_id: str, extra_ward_patterns: Optional[List[re.Pattern[str]]] = None) -> None:
        self._profile_id = profile_id
        self._wards = list(DEFAULT_WARDS)
        if extra_ward_patterns:
            for pat in extra_ward_patterns:
                self._wards.append((pat, f"profile ward ({profile_id})"))

    def load_identity_anchor(self) -> None:
        root = cogos_root()
        law_path = root / "law" / "root_law.json"
        anchor: Dict[str, Any] = {
            "name": "Nova",
            "role": "presentation_authority",
            "profile": self._profile_id,
            "loaded_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        }
        if law_path.exists():
            try:
                law = json.loads(law_path.read_text(encoding="utf-8-sig"))
                auth = law.get("authority", {})
                anchor["runtime_authority"] = auth.get("runtime_authority", "Jarvis")
                anchor["presentation_authority"] = auth.get("presentation_authority", "Nova")
            except (OSError, json.JSONDecodeError):
                pass
        if self._identity_path.exists():
            try:
                stored = json.loads(self._identity_path.read_text(encoding="utf-8-sig"))
                anchor.update(stored)
            except (OSError, json.JSONDecodeError):
                pass
        self._anchor = anchor
        self._identity_path.parent.mkdir(parents=True, exist_ok=True)
        self._identity_path.write_text(json.dumps(anchor, indent=2) + "\n", encoding="utf-8")

    @property
    def anchor(self) -> Dict[str, Any]:
        return dict(self._anchor)

    def integrity_check(self, text: str, context: Optional[Dict[str, Any]] = None) -> Tuple[bool, List[str]]:
        violations: List[str] = []
        for pattern, message in self._wards:
            if pattern.search(text):
                violations.append(message)
        if context and context.get("bypass_governance"):
            violations.append("Context requested governance bypass")
        return (len(violations) == 0, violations)

    def generate_response(
        self,
        user_input: str,
        mode: str = "automatic",
        context: Optional[Dict[str, Any]] = None,
    ) -> NovaOutput:
        ctx = context or {}
        ctx["user_input"] = user_input
        cmd = user_input.strip()
        lower = cmd.lower()

        if self._parse_automatic_intent(cmd, lower, ctx):
            action = ctx.get("automatic_action", "status")
            proposed = f"[Nova {mode}] Automatic mode: {action}"
        elif lower.startswith("substrate:") or lower.startswith("ul:"):
            source = cmd.split(":", 1)[1].strip()
            ctx["needs_ul"] = True
            ctx["ul_source"] = source
            proposed = f"[Nova {mode}] Running governed substrate: {source[:120]}"
        elif self._parse_creative_intent(lower, ctx):
            lane = ctx.get("creative_lane", "story_forge")
            proposed = f"[Nova {mode}] Starting governed {lane}: {cmd[:120]}"
        elif lower.startswith("creative:"):
            parts = cmd.split(":", 2)
            lane = parts[1].strip() if len(parts) > 1 else "story_forge"
            rest = parts[2].strip() if len(parts) > 2 else cmd
            ctx["needs_creative"] = True
            ctx["creative_lane"] = lane
            ctx["creative_verb"] = self._creative_verb_for_lane(lane)
            ctx["creative_prompt"] = rest
            proposed = f"[Nova {mode}] Creative lane {lane}: {rest[:100]}"
        elif lower in ("status", "health", "law"):
            proposed = (
                f"[Nova {mode}] CoGOS governed runtime active. "
                f"Anchor: {self._anchor.get('presentation_authority', 'Nova')}. "
                f"Mode: {mode}. Try 'substrate: agent pings x1' or 'mode manual'."
            )
        else:
            proposed = f"[Nova {mode}] {self._steady_response(cmd)}"

        ok, violations = self.integrity_check(proposed, ctx)
        realigned = False
        if not ok:
            proposed = "[Realigned per wards] " + proposed
            realigned = True

        return NovaOutput(
            text=proposed,
            mode=mode,
            confidence=0.85 if ok else 0.6,
            realigned=realigned,
        )

    def _parse_automatic_intent(self, cmd: str, lower: str, ctx: Dict[str, Any]) -> bool:
        if lower in ("automatic status", "auto status", "workspace status"):
            ctx["needs_automatic"] = True
            ctx["automatic_action"] = "status"
            return True
        if lower in ("suggest workflows", "workflow suggestions", "automatic suggestions"):
            ctx["needs_automatic"] = True
            ctx["automatic_action"] = "suggest"
            return True

        m = re.search(r"\b(?:create|new|start)\s+(?:a\s+)?(?:project|workspace)\s+(.+)$", cmd, re.I)
        if m:
            ctx["needs_automatic"] = True
            ctx["automatic_action"] = "workspace"
            ctx["workspace_name"] = m.group(1).strip()
            return True

        m = re.search(r"\borganize\s+(?:files\s+)?(?:in\s+)?(.+)$", cmd, re.I)
        if m and "governance" not in lower:
            source = m.group(1).strip().strip('"')
            apply = bool(re.search(r"\b(apply|move|now|do it)\b", lower))
            ctx["needs_automatic"] = True
            ctx["automatic_action"] = "organize"
            ctx["organize_source"] = source
            ctx["organize_apply"] = apply
            return True

        m = re.search(r"\bremember\s+(?:that\s+)?([^:]+):\s*(.+)$", cmd, re.I)
        if m:
            ctx["needs_automatic"] = True
            ctx["automatic_action"] = "remember"
            ctx["memory_key"] = m.group(1).strip()
            ctx["memory_value"] = m.group(2).strip()
            return True
        m = re.search(r"\bremember\s+that\s+(.+)$", cmd, re.I)
        if m:
            ctx["needs_automatic"] = True
            ctx["automatic_action"] = "remember"
            ctx["memory_key"] = "note"
            ctx["memory_value"] = m.group(1).strip()
            return True
        return False

    def _parse_creative_intent(self, lower: str, ctx: Dict[str, Any]) -> bool:
        """Natural language → creative lane (e.g. 'make dragon game')."""
        if re.search(r"\b(make|create|build)\b", lower) and re.search(
            r"\b(game|story|dragon|world)\b", lower
        ):
            ctx["needs_creative"] = True
            ctx["creative_prompt"] = ctx.get("user_input", lower)
            if "beat" in lower or "music" in lower or "score" in lower:
                ctx["creative_lane"] = "beatbox"
                ctx["creative_verb"] = "scores"
            elif "world" in lower or "3d" in lower:
                ctx["creative_lane"] = "world3d"
                ctx["creative_verb"] = "builds"
            else:
                ctx["creative_lane"] = "story_forge"
                ctx["creative_verb"] = "drafts"
            return True
        if "story forge" in lower or "storyforge" in lower:
            ctx["needs_creative"] = True
            ctx["creative_lane"] = "story_forge"
            ctx["creative_verb"] = "drafts"
            ctx["creative_prompt"] = lower
            return True
        if "beatbox" in lower or "beat box" in lower:
            ctx["needs_creative"] = True
            ctx["creative_lane"] = "beatbox"
            ctx["creative_verb"] = "scores"
            ctx["creative_prompt"] = lower
            return True
        return False

    def _creative_verb_for_lane(self, lane: str) -> str:
        return {
            "story_forge": "drafts",
            "beatbox": "scores",
            "world3d": "builds",
        }.get(lane, "drafts")

    def _steady_response(self, user_input: str) -> str:
        if not user_input:
            return "I'm here. What should we work on?"
        if user_input.endswith("?"):
            return f"Good question. I'll stay inside governed bounds while we explore: {user_input[:200]}"
        return f"Steady. I heard: {user_input[:200]}"
