"""
creative_modules.py — Governed Story Forge, Beat Box, and 3D world lanes (Phase 2).

Deterministic stubs write artifacts under memory/creative/. Full repo integration
can replace stubs without changing the UL substrate contract.
"""

from __future__ import annotations

import hashlib
import json
import re
import time
import uuid
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, List, Optional

from governance_invariant_engine import cogos_root


def _slug(text: str, max_len: int = 40) -> str:
    s = re.sub(r"[^a-z0-9]+", "-", text.lower()).strip("-")
    return (s[:max_len] or "artifact")


def _write_artifact(lane: str, kind: str, body: Dict[str, Any]) -> Path:
    root = cogos_root() / "memory" / "creative" / lane
    root.mkdir(parents=True, exist_ok=True)
    ts = time.strftime("%Y%m%d-%H%M%S", time.gmtime())
    name = f"{ts}-{_slug(kind)}-{uuid.uuid4().hex[:8]}.json"
    path = root / name
    record = {
        "kind": kind,
        "lane": lane,
        "timestamp": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "artifact_id": hashlib.sha256(json.dumps(body, sort_keys=True).encode()).hexdigest()[:16],
        **body,
    }
    path.write_text(json.dumps(record, indent=2) + "\n", encoding="utf-8")
    log = cogos_root() / "memory" / "creative" / "artifact_log.jsonl"
    with log.open("a", encoding="utf-8") as fh:
        fh.write(json.dumps({"path": str(path), "lane": lane, "kind": kind}) + "\n")
    return path


@dataclass
class CreativeResult:
    ok: bool
    lane: str
    summary: str
    artifact_path: str
    details: Dict[str, Any]


class StoryForgeLane:
    """Narrative draft lane — expression only, no governance bypass."""

    LANE = "story_forge"

    def draft(self, prompt: str, *, target: str = "game") -> CreativeResult:
        scenes = [
            {"id": "s1", "beat": "opening", "intent": "observe", "pacing": "medium"},
            {"id": "s2", "beat": "rising", "intent": "advance", "pacing": "fast"},
            {"id": "s3", "beat": "payoff", "intent": "confront", "pacing": "medium"},
        ]
        if "dragon" in prompt.lower():
            scenes.append({"id": "s4", "beat": "encounter", "intent": "confront", "tag": "dragon"})
        path = _write_artifact(
            self.LANE,
            "story_draft",
            {
                "prompt": prompt[:500],
                "target": target,
                "scenes": scenes,
                "temporal_shots": len(scenes),
                "deterministic": True,
            },
        )
        return CreativeResult(
            ok=True,
            lane=self.LANE,
            summary=f"Story draft: {len(scenes)} scenes for {target}",
            artifact_path=str(path),
            details={"scenes": len(scenes), "target": target},
        )

    def render(self, session_id: str = "") -> CreativeResult:
        sid = session_id or uuid.uuid4().hex[:12]
        path = _write_artifact(
            self.LANE,
            "render_manifest",
            {"session_id": sid, "status": "staged", "frames": 3, "deterministic": True},
        )
        return CreativeResult(
            ok=True,
            lane=self.LANE,
            summary=f"Render manifest staged for session {sid}",
            artifact_path=str(path),
            details={"session_id": sid},
        )


class BeatboxLane:
    """Audio production lane — score/live skeleton per BEATBOX_SPEC."""

    LANE = "beatbox"

    def score(self, scene_id: str = "scene-1", *, mood: str = "focused", bpm: int = 90) -> CreativeResult:
        path = _write_artifact(
            self.LANE,
            "beatbox_score",
            {
                "scene_id": scene_id,
                "mode": "score",
                "scene_state": {
                    "energy": 60,
                    "tension": 40,
                    "valence": 0.6,
                    "focus": 70,
                    "mood": mood,
                    "bpm": bpm,
                },
                "audio_path": f"/opt/cogos/memory/creative/beatbox/{scene_id}-score.wav",
                "deterministic_fallback": True,
            },
        )
        return CreativeResult(
            ok=True,
            lane=self.LANE,
            summary=f"Beatbox score mode: {mood} @ {bpm}bpm",
            artifact_path=str(path),
            details={"scene_id": scene_id, "bpm": bpm},
        )

    def mix(self, session_id: str = "") -> CreativeResult:
        sid = session_id or uuid.uuid4().hex[:12]
        path = _write_artifact(
            self.LANE,
            "beatbox_mix",
            {"session_id": sid, "mode": "live", "status": "mixed", "tracks": 2},
        )
        return CreativeResult(
            ok=True,
            lane=self.LANE,
            summary=f"Beatbox mix complete for {sid}",
            artifact_path=str(path),
            details={"session_id": sid},
        )


class World3DLane:
    """Minimal 3D/world compiler hook — UL-governed stub."""

    LANE = "world3d"

    def build(self, prompt: str) -> CreativeResult:
        path = _write_artifact(
            self.LANE,
            "world_build",
            {
                "prompt": prompt[:300],
                "primitives": ["ground_plane", "spawn_point", "sky_dome"],
                "format": "ul_world_v1",
                "deterministic": True,
            },
        )
        return CreativeResult(
            ok=True,
            lane=self.LANE,
            summary="World build stub (3 primitives)",
            artifact_path=str(path),
            details={"primitives": 3},
        )


_LANES = {
    "story_forge": StoryForgeLane(),
    "beatbox": BeatboxLane(),
    "world3d": World3DLane(),
}


def run_creative(
    lane: str,
    verb: str,
    *,
    prompt: str = "",
    context: Optional[Dict[str, Any]] = None,
) -> CreativeResult:
    ctx = context or {}
    if lane not in _LANES:
        return CreativeResult(False, lane, f"unknown lane: {lane}", "", {})

    mod = _LANES[lane]
    if lane == "story_forge":
        if verb in ("drafts", "draft"):
            return mod.draft(prompt or ctx.get("prompt", "untitled"), target=ctx.get("target", "game"))
        if verb in ("renders", "render"):
            return mod.render(ctx.get("session_id", ""))
    if lane == "beatbox":
        if verb in ("scores", "score"):
            return mod.score(ctx.get("scene_id", "scene-1"), mood=ctx.get("mood", "focused"))
        if verb in ("mixes", "mix"):
            return mod.mix(ctx.get("session_id", ""))
    if lane == "world3d" and verb in ("builds", "build"):
        return mod.build(prompt or ctx.get("prompt", "world"))

    return CreativeResult(False, lane, f"verb {verb} not supported on {lane}", "", {})
