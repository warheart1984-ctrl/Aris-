"""
compute_tiers.py — Capability tiers (base / standard / elevated / developer).
"""

from __future__ import annotations

import json
import os
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, List, Optional

from governance_invariant_engine import cogos_root


@dataclass
class TierCheckResult:
    allowed: bool
    tier: str
    capability: str
    reason: str = ""


class ComputeTierEngine:
    def __init__(self, path: Optional[Path] = None) -> None:
        self.path = path or (cogos_root() / "config" / "compute_tiers.json")
        self._data = self._load()
        self._override = os.environ.get("COGOS_COMPUTE_TIER", "").strip()

    def _load(self) -> Dict[str, Any]:
        if not self.path.exists():
            return {"tiers": {}, "default_tier": "standard"}
        return json.loads(self.path.read_text(encoding="utf-8-sig"))

    def tier_for_profile(self, profile_id: str) -> str:
        if self._override and self._override in self._data.get("tiers", {}):
            return self._override
        mapping = self._data.get("profile_tier_map", {})
        return str(mapping.get(profile_id, self._data.get("default_tier", "standard")))

    def resolve_tier(self, profile_id: str = "operator") -> str:
        return self.tier_for_profile(profile_id)

    def tier_def(self, tier: str) -> Dict[str, Any]:
        return dict(self._data.get("tiers", {}).get(tier, {}))

    def list_tiers(self) -> List[Dict[str, Any]]:
        out = []
        for tid, raw in self._data.get("tiers", {}).items():
            out.append({"id": tid, "label": raw.get("label", tid), "capabilities": len(raw.get("capabilities", []))})
        return out

    def check(self, capability: str, *, profile_id: str = "operator") -> TierCheckResult:
        tier = self.resolve_tier(profile_id)
        tdef = self.tier_def(tier)
        caps = list(tdef.get("capabilities", []))
        denies = list(tdef.get("denies", []))

        if capability in denies:
            return TierCheckResult(False, tier, capability, f"denied by tier {tier}")

        if "*" in caps:
            return TierCheckResult(True, tier, capability)

        if capability in caps:
            return TierCheckResult(True, tier, capability)

        # Prefix match e.g. creative.* for creative.story_draft
        prefix = capability.split(".")[0] + ".*"
        if prefix in caps or any(c.endswith(".*") and capability.startswith(c[:-1]) for c in caps):
            return TierCheckResult(True, tier, capability)

        return TierCheckResult(False, tier, capability, f"capability not in tier {tier}")

    def check_ul_capability(self, ul_cap: str, *, profile_id: str = "operator") -> TierCheckResult:
        mapping = {
            "harmless": "ul.harmless",
            "query": "ul.query",
            "mutate": "ul.mutate",
            "dangerous": "ul.dangerous",
            "privileged": "ul.privileged",
        }
        return self.check(mapping.get(ul_cap, f"ul.{ul_cap}"), profile_id=profile_id)

    def check_creative(self, lane: str, verb: str, *, profile_id: str = "operator") -> TierCheckResult:
        if verb in ("drafts", "draft"):
            cap = "creative.story_draft"
        elif verb in ("renders", "render"):
            cap = "creative.render"
        elif verb in ("scores", "score"):
            cap = "creative.beatbox_score"
        elif verb in ("builds", "build"):
            cap = "creative.world_build"
        else:
            cap = f"creative.{lane}"
        return self.check(cap, profile_id=profile_id)

    def log_denial(self, result: TierCheckResult, *, context: Optional[Dict[str, Any]] = None) -> None:
        log = cogos_root() / "memory" / "traces" / "tier_denials.jsonl"
        log.parent.mkdir(parents=True, exist_ok=True)
        row = {
            "ts": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
            "tier": result.tier,
            "capability": result.capability,
            "reason": result.reason,
            "context": context or {},
        }
        with log.open("a", encoding="utf-8") as fh:
            fh.write(json.dumps(row) + "\n")
