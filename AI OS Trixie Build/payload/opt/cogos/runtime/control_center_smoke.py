"""Smoke checks for the CoGOS Control Center UI and action surface."""

from __future__ import annotations

import importlib.util
import json
import shutil
from pathlib import Path

from automatic_mode import AutomaticModeEngine
from governance_invariant_engine import cogos_root


def _load_desktop_module():
    root = cogos_root()
    path = root / "bin" / "cogos_desktop.py"
    spec = importlib.util.spec_from_file_location("cogos_desktop_smoke", path)
    if not spec or not spec.loader:
        raise RuntimeError("could not load cogos_desktop.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _cleanup(engine: AutomaticModeEngine) -> None:
    cleanup_ids = {"control-center-smoke"}
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
            if row.get("detail", {}).get("workspace_id") in cleanup_ids:
                continue
            kept.append(row)
        engine.events_path.write_text("".join(json.dumps(row, sort_keys=True) + "\n" for row in kept), encoding="utf-8")
    engine._write_suggestions()
    last = cogos_root() / "memory" / "logs" / "control_center_last_action.json"
    last.unlink(missing_ok=True)


def main() -> int:
    module = _load_desktop_module()
    data = module.control_center_status()
    html = module.render_desktop(data).decode("utf-8")
    assert "CoGOS Control Center" in html
    assert "Automatic" in html
    assert "Packages And Backup" in html
    assert "Install And Persistence" in html

    result = module.handle_action(
        "auto_workspace",
        {"workspace_name": ["Control Center Smoke"], "profile_id": ["operator"]},
    )
    assert result.get("ok")
    refreshed = module.control_center_status()
    assert refreshed["phase3"]["automatic"]["workspace_count"] >= 1

    module.write_last_action("auto_workspace", result)
    assert module.last_action().get("action") == "auto_workspace"

    _cleanup(AutomaticModeEngine())
    print("control_center_smoke: ALL PASSED")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
