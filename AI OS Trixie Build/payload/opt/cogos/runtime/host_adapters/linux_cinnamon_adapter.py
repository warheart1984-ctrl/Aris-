"""Linux + Cinnamon desktop host adapter (primary path)."""

from __future__ import annotations

import json
import os
import subprocess
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

LINUX_CINNAMON_HOST_NAME = "linux-cinnamon"
LINUX_CINNAMON_VERSION = "debian-cinnamon-live"

LINUX_CINNAMON_CAPABILITIES: tuple[str, ...] = (
    "governance",
    "lineage",
    "identity_preservation",
    "session",
    "display",
    "user_login",
    "process_observe",
    "journal_observe",
    "systemd_observe",
    "cgroup_observe",
    "proc_observe",
)


@dataclass(frozen=True, slots=True)
class HostDeclaration:
    name: str
    version: str
    capabilities: tuple[str, ...] = field(default_factory=tuple)
    legitimacy_token: str = ""
    session_binding: str = ""
    host_class: str = "external"

    def as_dict(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "version": self.version,
            "capabilities": list(self.capabilities),
            "legitimacy_token": self.legitimacy_token,
            "session_binding": self.session_binding,
            "host_class": self.host_class,
        }


def _run(cmd: list[str], *, timeout: float = 3.0) -> str:
    try:
        completed = subprocess.run(
            cmd,
            check=False,
            capture_output=True,
            text=True,
            timeout=timeout,
        )
        if completed.returncode != 0:
            return ""
        return (completed.stdout or "").strip()
    except (OSError, subprocess.SubprocessError):
        return ""


def _read_text(path: Path, limit: int = 65536) -> str:
    try:
        return path.read_text(encoding="utf-8", errors="replace")[:limit]
    except OSError:
        return ""


def build_host_declaration(
    *,
    legitimacy_token: str,
    session_binding: str,
    version: str = LINUX_CINNAMON_VERSION,
) -> HostDeclaration:
    return HostDeclaration(
        name=LINUX_CINNAMON_HOST_NAME,
        version=version,
        capabilities=LINUX_CINNAMON_CAPABILITIES,
        legitimacy_token=legitimacy_token,
        session_binding=session_binding,
        host_class="external",
    )


def observe_state_registers() -> dict[str, Any]:
    session = {
        "xdg_session_id": os.environ.get("XDG_SESSION_ID", ""),
        "xdg_session_type": os.environ.get("XDG_SESSION_TYPE", ""),
        "desktop": os.environ.get("XDG_CURRENT_DESKTOP", ""),
        "user": os.environ.get("USER", ""),
    }
    processes = {"count": 0, "sample": []}
    proc_root = Path("/proc")
    if proc_root.is_dir():
        pids = sorted(int(name) for name in os.listdir(proc_root) if name.isdigit())[:8]
        processes["count"] = len([n for n in os.listdir(proc_root) if n.isdigit()])
        for pid in pids:
            cmdline = _read_text(proc_root / str(pid) / "cmdline", limit=256).replace("\x00", " ")
            processes["sample"].append({"pid": pid, "cmdline": cmdline[:200]})

    services = {"systemd": {"active": [], "failed": []}}
    active = _run(["systemctl", "list-units", "--type=service", "--state=active", "--no-pager", "--no-legend"])
    failed = _run(["systemctl", "list-units", "--type=service", "--state=failed", "--no-pager", "--no-legend"])
    if active:
        services["systemd"]["active"] = [line.split()[0] for line in active.splitlines()[:12] if line.strip()]
    if failed:
        services["systemd"]["failed"] = [line.split()[0] for line in failed.splitlines()[:8] if line.strip()]

    identities = {"loginctl": []}
    sessions = _run(["loginctl", "list-sessions", "--no-legend"])
    if sessions:
        identities["loginctl"] = [line.split()[0] for line in sessions.splitlines()[:8] if line.strip()]

    cgroups: dict[str, Any] = {}
    cgroup_root = Path("/sys/fs/cgroup")
    if cgroup_root.is_dir():
        cgroups["root"] = str(cgroup_root)
        cgroups["controllers"] = [child.name for child in cgroup_root.iterdir() if child.is_dir()][:16]

    journal: dict[str, Any] = {"recent": []}
    journal_lines = _run(["journalctl", "--no-pager", "-n", "8", "-o", "json"], timeout=5.0)
    if journal_lines:
        for line in journal_lines.splitlines():
            try:
                journal["recent"].append(json.loads(line))
            except json.JSONDecodeError:
                continue

    return {
        "session": session,
        "processes": processes,
        "services": services,
        "identities": identities,
        "cgroups": cgroups,
        "journal": journal,
    }


def observe_meta_registers(*, governor_version: str = "0.12") -> dict[str, Any]:
    uname = _run(["uname", "-sr"])
    init_target = ""
    for candidate in (Path("/usr/sbin/init"), Path("/sbin/init")):
        if candidate.exists():
            try:
                init_target = os.readlink(candidate)
            except OSError:
                init_target = str(candidate)
            break
    return {
        "host": {
            "name": LINUX_CINNAMON_HOST_NAME,
            "host_class": "external",
            "version": LINUX_CINNAMON_VERSION,
            "capabilities": list(LINUX_CINNAMON_CAPABILITIES),
            "desktop": os.environ.get("XDG_CURRENT_DESKTOP", "Cinnamon"),
            "init": init_target,
            "kernel": uname,
        },
        "governor_version": governor_version,
        "substrate": "debian-live-cinnamon",
    }


def host_meta_for_canonical(*, governor_version: str = "0.12") -> dict[str, Any]:
    return dict(observe_meta_registers(governor_version=governor_version)["host"])
