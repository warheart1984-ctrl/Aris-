"""
user_profiles.py — Minimal user model (operator + kid) with profile-bound wards.
"""

from __future__ import annotations

import json
import os
import re
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional

from governance_invariant_engine import cogos_root


@dataclass
class UserProfile:
    id: str
    display_name: str
    tier: str
    mode_default: str
    home_hint: str
    wards_extra: List[str] = field(default_factory=list)

    def extra_ward_patterns(self) -> List[re.Pattern[str]]:
        return [re.compile(p, re.I) for p in self.wards_extra]


class UserProfileManager:
    def __init__(self, path: Optional[Path] = None) -> None:
        self.path = path or (cogos_root() / "config" / "users.json")
        self._data: Dict[str, Any] = {}
        self.reload()

    def reload(self) -> None:
        if not self.path.exists():
            self._data = {
                "version": "1.0",
                "active_profile": "operator",
                "profiles": {
                    "operator": {
                        "display_name": "Operator",
                        "tier": "operator",
                        "mode_default": "manual",
                        "home_hint": "/home/operator",
                        "wards_extra": [],
                    }
                },
            }
            return
        self._data = json.loads(self.path.read_text(encoding="utf-8-sig"))

    def save(self) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.path.write_text(json.dumps(self._data, indent=2) + "\n", encoding="utf-8")

    @property
    def active_id(self) -> str:
        env = os.environ.get("COGOS_PROFILE", "").strip()
        if env and env in self._data.get("profiles", {}):
            return env
        return str(self._data.get("active_profile", "operator"))

    def set_active(self, profile_id: str) -> None:
        if profile_id not in self._data.get("profiles", {}):
            raise ValueError(f"unknown profile: {profile_id}")
        self._data["active_profile"] = profile_id
        self.save()
        self._log_switch(profile_id)

    def get_active(self) -> UserProfile:
        return self.get(self.active_id)

    def get(self, profile_id: str) -> UserProfile:
        raw = self._data.get("profiles", {}).get(profile_id)
        if not raw:
            raise ValueError(f"unknown profile: {profile_id}")
        return UserProfile(
            id=profile_id,
            display_name=str(raw.get("display_name", profile_id)),
            tier=str(raw.get("tier", "operator")),
            mode_default=str(raw.get("mode_default", "automatic")),
            home_hint=str(raw.get("home_hint", "")),
            wards_extra=list(raw.get("wards_extra", [])),
        )

    def list_profiles(self) -> List[Dict[str, Any]]:
        active = self.active_id
        out = []
        for pid, raw in self._data.get("profiles", {}).items():
            out.append({
                "id": pid,
                "display_name": raw.get("display_name", pid),
                "tier": raw.get("tier"),
                "active": pid == active,
            })
        return out

    def _log_switch(self, profile_id: str) -> None:
        log_path = cogos_root() / "memory" / "operator" / "profile_switches.jsonl"
        log_path.parent.mkdir(parents=True, exist_ok=True)
        row = {
            "ts": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
            "profile": profile_id,
            "user": os.environ.get("USER", ""),
        }
        with log_path.open("a", encoding="utf-8") as fh:
            fh.write(json.dumps(row) + "\n")
