"""First-run wizard state and setup actions for CoGOS."""

from __future__ import annotations

import json
import re
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, Optional

from automatic_mode import AutomaticModeEngine, slugify
from governance_invariant_engine import cogos_root


def utc_now() -> str:
    return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())


def _read_json(path: Path, default: Any) -> Any:
    try:
        return json.loads(path.read_text(encoding="utf-8-sig"))
    except Exception:
        return default


def _write_json(path: Path, data: Dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def _clean_id(value: str, fallback: str = "operator") -> str:
    out = re.sub(r"[^a-z0-9_-]+", "-", str(value).strip().lower()).strip("-")
    return out[:40] or fallback


def _clean_hostname(value: str) -> str:
    out = re.sub(r"[^a-zA-Z0-9-]+", "-", str(value).strip()).strip("-")
    return (out[:63] or "cogos").lower()


@dataclass
class FirstRunWizard:
    root: Path = cogos_root()

    def __post_init__(self) -> None:
        self.state_path = self.root / "config" / "first_run.json"
        self.proof_path = self.root / "memory" / "logs" / "first_run_proof.json"
        self.events_path = self.root / "memory" / "operator" / "first_run_events.jsonl"

    def status(self) -> Dict[str, Any]:
        state = _read_json(self.state_path, {})
        completed = bool(state.get("completed"))
        return {
            "ok": True,
            "completed": completed,
            "state": state,
            "proof_path": str(self.proof_path),
            "needs_wizard": not completed,
            "defaults": self.defaults(),
        }

    def defaults(self) -> Dict[str, Any]:
        users = _read_json(self.root / "config" / "users.json", {})
        active = users.get("active_profile", "operator")
        profile = users.get("profiles", {}).get(active, {})
        return {
            "hostname": _read_hostname() or "cogos",
            "profile_id": active,
            "display_name": profile.get("display_name", "Operator"),
            "mode_default": profile.get("mode_default", "manual"),
            "workspace_name": "Home Base",
            "kid_profile": "true" if "kid" in users.get("profiles", {}) else "false",
        }

    def apply(
        self,
        *,
        hostname: str = "cogos",
        profile_id: str = "operator",
        display_name: str = "Operator",
        mode_default: str = "manual",
        workspace_name: str = "Home Base",
        enable_kid: bool = True,
    ) -> Dict[str, Any]:
        profile_id = _clean_id(profile_id)
        hostname = _clean_hostname(hostname)
        mode_default = mode_default if mode_default in ("manual", "automatic") else "manual"
        display_name = str(display_name).strip()[:80] or "Operator"
        workspace_name = str(workspace_name).strip()[:100] or "Home Base"

        users = _read_json(self.root / "config" / "users.json", {"version": "1.0", "profiles": {}})
        profiles = users.setdefault("profiles", {})
        profiles[profile_id] = {
            "display_name": display_name,
            "tier": "operator",
            "mode_default": mode_default,
            "home_hint": f"/home/{profile_id}",
            "wards_extra": [],
        }
        if enable_kid:
            profiles.setdefault(
                "kid",
                {
                    "display_name": "Kid",
                    "tier": "restricted-runtime",
                    "mode_default": "automatic",
                    "home_hint": "/home/kid",
                    "wards_extra": [r"\bpassword\b", r"\bcredit\s*card\b", r"\bdelete\s+all\b"],
                },
            )
        users["active_profile"] = profile_id
        _write_json(self.root / "config" / "users.json", users)

        boot_profile = _read_json(self.root / "config" / "boot_profile.json", {})
        boot_profile["first_run_completed"] = True
        boot_profile["operator_message"] = "CoGOS first-run setup complete. Use Control Center for profiles, backup, install, and device storage."
        _write_json(self.root / "config" / "boot_profile.json", boot_profile)

        _write_hostname_hint(self.root, hostname)
        workspace = AutomaticModeEngine().create_workspace(workspace_name, profile_id=profile_id)

        state = {
            "completed": True,
            "completed_at": utc_now(),
            "hostname": hostname,
            "profile_id": profile_id,
            "display_name": display_name,
            "mode_default": mode_default,
            "workspace": workspace.get("workspace", {}),
            "kid_profile_enabled": enable_kid,
        }
        _write_json(self.state_path, state)
        _write_json(self.proof_path, {"ok": True, "kind": "first_run", **state})
        self._event("complete", state)
        return {"ok": True, "first_run": state}

    def reset(self) -> Dict[str, Any]:
        state = _read_json(self.state_path, {})
        reset_path = self.root / "memory" / "logs" / f"first_run_reset_{int(time.time())}.json"
        if state:
            _write_json(reset_path, state)
        if self.state_path.exists():
            self.state_path.unlink()
        self._event("reset", {"backup": str(reset_path) if state else None})
        return {"ok": True, "completed": False, "backup": str(reset_path) if state else None}

    def _event(self, kind: str, detail: Dict[str, Any]) -> None:
        self.events_path.parent.mkdir(parents=True, exist_ok=True)
        with self.events_path.open("a", encoding="utf-8") as fh:
            fh.write(json.dumps({"ts": utc_now(), "kind": kind, "detail": detail}, sort_keys=True) + "\n")


def _read_hostname() -> str:
    try:
        return Path("/etc/hostname").read_text(encoding="utf-8").strip()
    except Exception:
        return ""


def _write_hostname_hint(root: Path, hostname: str) -> None:
    hint = root / "config" / "hostname.json"
    _write_json(hint, {"hostname": hostname, "updated_at": utc_now(), "note": "Applied to installed system by cogos-install or operator setup."})

