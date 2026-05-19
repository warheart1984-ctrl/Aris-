"""
phase2_panels.py — Creative stack + mesh status for LawPulse / desktop.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict, List

from governance_invariant_engine import cogos_root


def _read_jsonl(path: Path, limit: int = 15) -> List[Dict[str, Any]]:
    if not path.exists():
        return []
    rows = []
    for line in path.read_text(encoding="utf-8", errors="replace").strip().splitlines()[-limit:]:
        try:
            rows.append(json.loads(line))
        except json.JSONDecodeError:
            continue
    return rows


def creative_status() -> Dict[str, Any]:
    root = cogos_root()
    creative = root / "memory" / "creative"
    log = _read_jsonl(creative / "artifact_log.jsonl", 10)
    by_lane: Dict[str, int] = {}
    for row in log:
        lane = row.get("lane", "unknown")
        by_lane[lane] = by_lane.get(lane, 0) + 1
    latest = log[-1] if log else {}
    return {
        "artifacts_total": len(log),
        "by_lane": by_lane,
        "latest": latest,
        "lanes": ["story_forge", "beatbox", "world3d"],
    }


def mesh_status() -> Dict[str, Any]:
    try:
        from mesh_identity import MeshIdentityStore
        from reasoning_exchange import ReasoningExchangeNode

        node = ReasoningExchangeNode()
        recent = node.list_recent(10)
        net_flows = _read_jsonl(cogos_root() / "memory" / "traces" / "net_gre.jsonl", 5)
        return {
            "identity": MeshIdentityStore().export_exchange_bundle(),
            "trusted_peers": recent.get("trusted_count", 0),
            "inbox_recent": len(recent.get("inbox", [])),
            "outbox_recent": len(recent.get("outbox", [])),
            "net_gre_flows": net_flows,
            "mesh_name": json.loads(
                (cogos_root() / "config" / "mesh.json").read_text(encoding="utf-8-sig")
            ).get("mesh_name", "infi-family")
            if (cogos_root() / "config" / "mesh.json").exists()
            else "infi-family",
        }
    except Exception as exc:
        return {"error": str(exc)}


def phase2_status() -> Dict[str, Any]:
    return {"creative": creative_status(), "mesh": mesh_status()}


def network_visibility() -> List[Dict[str, Any]]:
    """Human-readable 'what is talking to what' for LawPulse."""
    flows = _read_jsonl(cogos_root() / "memory" / "traces" / "net_gre.jsonl", 12)
    out = []
    for row in flows:
        f = row.get("flow", {})
        out.append({
            "direction": f.get("direction"),
            "target": f"{f.get('host')}:{f.get('port')}",
            "module": f.get("module_id"),
            "profile": f.get("profile_id"),
            "allowed": row.get("allowed"),
        })
    mesh = mesh_status()
    if mesh.get("identity"):
        out.append({
            "direction": "mesh",
            "target": mesh.get("mesh_name"),
            "module": "reasoning_exchange",
            "profile": mesh["identity"].get("device_id", "")[:8],
            "allowed": True,
        })
    return out
