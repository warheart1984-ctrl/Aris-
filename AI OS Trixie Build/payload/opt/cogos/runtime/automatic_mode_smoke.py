"""Smoke checks for CoGOS Automatic mode."""

from __future__ import annotations

import tempfile
import json
import shutil
from pathlib import Path

from automatic_mode import AutomaticModeEngine
from cogos_runtime import CognitiveRuntime


def _cleanup_smoke_state(engine: AutomaticModeEngine) -> None:
    cleanup_ids = {"automatic-smoke", "family-photos"}
    state = engine._load_state()
    for wid in cleanup_ids:
        state.get("workspaces", {}).pop(wid, None)
        state.get("memory", {}).pop(wid, None)
        shutil.rmtree(engine.workspace_root / wid, ignore_errors=True)
    if state.get("active_workspace") in cleanup_ids:
        state["active_workspace"] = None
    engine._save_state(state)

    if engine.events_path.exists():
        kept = []
        for line in engine.events_path.read_text(encoding="utf-8-sig").splitlines():
            try:
                row = json.loads(line)
            except Exception:
                continue
            detail = row.get("detail", {})
            if detail.get("workspace_id") in cleanup_ids:
                continue
            if str(detail.get("source", "")).find("tmp") >= 0 and row.get("kind") == "files.organize":
                continue
            kept.append(row)
        engine.events_path.write_text("".join(json.dumps(row, sort_keys=True) + "\n" for row in kept), encoding="utf-8")
    engine._write_suggestions()


def main() -> int:
    engine = AutomaticModeEngine()
    with tempfile.TemporaryDirectory() as td:
        source = Path(td) / "source"
        source.mkdir()
        (source / "notes.txt").write_text("hello", encoding="utf-8")
        (source / "photo.png").write_bytes(b"png")

        ws = engine.create_workspace("Automatic Smoke")
        assert ws["ok"]
        workspace_id = ws["workspace"]["id"]

        plan = engine.organize_files(str(source), workspace_id=workspace_id, apply=False)
        assert plan["ok"] and plan["planned"] == 2 and plan["moved"] == 0

        moved = engine.organize_files(str(source), workspace_id=workspace_id, apply=True)
        assert moved["ok"] and moved["moved"] == 2

        remembered = engine.remember("goal", "make automatic mode useful", workspace_id=workspace_id)
        assert remembered["ok"]

        suggestions = engine.suggest_workflows()
        assert suggestions["ok"]

        rt = CognitiveRuntime()
        assert rt.boot()
        rt.set_mode("automatic")
        response = rt.process("create workspace Family Photos")
        assert "AUTOMATIC OK" in response
        response = rt.process("remember camera import: put photos in Family Photos")
        assert "AUTOMATIC OK" in response

    _cleanup_smoke_state(engine)
    print("automatic_mode_smoke: ALL PASSED")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
