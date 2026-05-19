"""Automatic mode: normal-user workspaces, memory, file organization, workflows."""

from __future__ import annotations

import json
import re
import shutil
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional

from governance_invariant_engine import cogos_root


CATEGORIES = {
    "Documents": {".pdf", ".doc", ".docx", ".txt", ".md", ".rtf", ".odt", ".xls", ".xlsx", ".ppt", ".pptx"},
    "Images": {".png", ".jpg", ".jpeg", ".gif", ".webp", ".bmp", ".svg", ".heic"},
    "Audio": {".mp3", ".wav", ".flac", ".ogg", ".m4a"},
    "Video": {".mp4", ".mov", ".avi", ".mkv", ".webm"},
    "Archives": {".zip", ".7z", ".rar", ".tar", ".gz", ".xz", ".iso"},
    "Code": {".py", ".js", ".ts", ".tsx", ".jsx", ".rs", ".go", ".java", ".c", ".cpp", ".h", ".json", ".toml", ".yaml", ".yml", ".ul", ".ulsub"},
}


def now() -> str:
    return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())


def slugify(text: str) -> str:
    slug = re.sub(r"[^a-z0-9]+", "-", text.strip().lower()).strip("-")
    return slug[:60] or "workspace"


def category_for(path: Path) -> str:
    suffix = path.suffix.lower()
    for category, suffixes in CATEGORIES.items():
        if suffix in suffixes:
            return category
    return "Other"


@dataclass
class AutomaticModeEngine:
    root: Path = cogos_root()

    def __post_init__(self) -> None:
        self.base = self.root / "memory" / "automatic"
        self.workspace_root = self.root / "memory" / "workspaces"
        self.state_path = self.base / "state.json"
        self.events_path = self.base / "events.jsonl"
        self.suggestions_path = self.base / "workflow_suggestions.json"
        self.base.mkdir(parents=True, exist_ok=True)
        self.workspace_root.mkdir(parents=True, exist_ok=True)

    def _load_state(self) -> Dict[str, Any]:
        if not self.state_path.exists():
            return {"version": "1.0", "active_workspace": None, "workspaces": {}, "memory": {}}
        try:
            return json.loads(self.state_path.read_text(encoding="utf-8-sig"))
        except Exception:
            return {"version": "1.0", "active_workspace": None, "workspaces": {}, "memory": {}}

    def _save_state(self, state: Dict[str, Any]) -> None:
        self.state_path.parent.mkdir(parents=True, exist_ok=True)
        self.state_path.write_text(json.dumps(state, indent=2, sort_keys=True) + "\n", encoding="utf-8")

    def _event(self, kind: str, detail: Dict[str, Any]) -> None:
        row = {"ts": now(), "kind": kind, "detail": detail}
        with self.events_path.open("a", encoding="utf-8") as fh:
            fh.write(json.dumps(row, sort_keys=True) + "\n")

    def create_workspace(self, name: str, *, profile_id: str = "operator") -> Dict[str, Any]:
        workspace_id = slugify(name)
        path = self.workspace_root / workspace_id
        for rel in ("inbox", "notes", "artifacts", "workflows", "exports"):
            (path / rel).mkdir(parents=True, exist_ok=True)
        readme = path / "notes" / "README.md"
        if not readme.exists():
            readme.write_text(f"# {name}\n\nCreated by CoGOS Automatic mode on {now()}.\n", encoding="utf-8")
        state = self._load_state()
        state.setdefault("workspaces", {})[workspace_id] = {
            "id": workspace_id,
            "name": name,
            "path": str(path),
            "profile_id": profile_id,
            "created_at": state.get("workspaces", {}).get(workspace_id, {}).get("created_at") or now(),
            "updated_at": now(),
        }
        state["active_workspace"] = workspace_id
        self._save_state(state)
        self._event("workspace.create", {"workspace_id": workspace_id, "name": name, "path": str(path)})
        return {"ok": True, "workspace": state["workspaces"][workspace_id]}

    def active_workspace(self) -> Optional[Dict[str, Any]]:
        state = self._load_state()
        active = state.get("active_workspace")
        if not active:
            return None
        return state.get("workspaces", {}).get(active)

    def remember(self, key: str, value: str, *, workspace_id: Optional[str] = None) -> Dict[str, Any]:
        state = self._load_state()
        workspace_id = workspace_id or state.get("active_workspace")
        memory = state.setdefault("memory", {})
        bucket = memory.setdefault(workspace_id or "global", {})
        bucket[key] = {"value": value, "updated_at": now()}
        self._save_state(state)
        self._event("memory.remember", {"workspace_id": workspace_id, "key": key, "value_preview": value[:120]})
        return {"ok": True, "workspace_id": workspace_id, "key": key, "value": value}

    def _iter_files(self, source: Path) -> Iterable[Path]:
        for item in sorted(source.iterdir(), key=lambda p: p.name.lower()):
            if item.name.startswith(".") or item.is_dir():
                continue
            if item.is_file():
                yield item

    def organize_files(
        self,
        source_dir: str,
        *,
        workspace_id: Optional[str] = None,
        apply: bool = False,
    ) -> Dict[str, Any]:
        source = Path(source_dir).expanduser()
        if not source.exists() or not source.is_dir():
            return {"ok": False, "reason": f"source directory not found: {source}"}

        state = self._load_state()
        workspace_id = workspace_id or state.get("active_workspace")
        if not workspace_id:
            created = self.create_workspace(source.name or "organized-files")
            workspace_id = created["workspace"]["id"]
            state = self._load_state()
        workspace = state.get("workspaces", {}).get(workspace_id)
        if not workspace:
            return {"ok": False, "reason": f"workspace not found: {workspace_id}"}

        target_root = Path(workspace["path"]) / "inbox"
        plan: List[Dict[str, Any]] = []
        for src in self._iter_files(source):
            category = category_for(src)
            dst = target_root / category / src.name
            counter = 1
            while dst.exists() and dst.resolve() != src.resolve():
                dst = target_root / category / f"{src.stem}-{counter}{src.suffix}"
                counter += 1
            plan.append({"source": str(src), "target": str(dst), "category": category})

        moved: List[Dict[str, Any]] = []
        if apply:
            for item in plan:
                src = Path(item["source"])
                dst = Path(item["target"])
                dst.parent.mkdir(parents=True, exist_ok=True)
                if src.exists() and src.resolve() != dst.resolve():
                    shutil.move(str(src), str(dst))
                    moved.append(item)

        summary = {
            "ok": True,
            "workspace_id": workspace_id,
            "source": str(source),
            "target_root": str(target_root),
            "planned": len(plan),
            "moved": len(moved),
            "apply": apply,
            "plan": plan[:100],
        }
        self._event("files.organize", {k: v for k, v in summary.items() if k != "plan"})
        self._write_suggestions()
        return summary

    def _recent_events(self, limit: int = 200) -> List[Dict[str, Any]]:
        if not self.events_path.exists():
            return []
        rows: List[Dict[str, Any]] = []
        for line in self.events_path.read_text(encoding="utf-8-sig").splitlines()[-limit:]:
            try:
                rows.append(json.loads(line))
            except Exception:
                continue
        return rows

    def _write_suggestions(self) -> List[Dict[str, Any]]:
        events = self._recent_events()
        organize_by_source: Dict[str, int] = {}
        workspace_touch: Dict[str, int] = {}
        for event in events:
            detail = event.get("detail", {})
            if event.get("kind") == "files.organize":
                source = detail.get("source", "")
                organize_by_source[source] = organize_by_source.get(source, 0) + 1
            if detail.get("workspace_id"):
                workspace_touch[detail["workspace_id"]] = workspace_touch.get(detail["workspace_id"], 0) + 1

        suggestions: List[Dict[str, Any]] = []
        for source, count in sorted(organize_by_source.items(), key=lambda x: x[1], reverse=True):
            if count >= 2:
                suggestions.append({
                    "id": f"auto-organize-{slugify(source)}",
                    "kind": "workflow",
                    "title": f"Auto-organize {Path(source).name or source}",
                    "reason": f"Organized this location {count} times.",
                    "proposal": {"trigger": "new_files", "source": source, "action": "organize_into_active_workspace"},
                })
        for workspace_id, count in sorted(workspace_touch.items(), key=lambda x: x[1], reverse=True):
            if count >= 3:
                suggestions.append({
                    "id": f"workspace-brief-{workspace_id}",
                    "kind": "workflow",
                    "title": f"Daily brief for {workspace_id}",
                    "reason": f"Workspace touched {count} times recently.",
                    "proposal": {"trigger": "daily", "workspace_id": workspace_id, "action": "summarize_state"},
                })

        self.suggestions_path.write_text(json.dumps(suggestions[:20], indent=2) + "\n", encoding="utf-8")
        return suggestions[:20]

    def suggest_workflows(self) -> Dict[str, Any]:
        suggestions = self._write_suggestions()
        self._event("workflow.suggest", {"count": len(suggestions)})
        return {"ok": True, "suggestions": suggestions}

    def status(self) -> Dict[str, Any]:
        state = self._load_state()
        suggestions = []
        if self.suggestions_path.exists():
            try:
                suggestions = json.loads(self.suggestions_path.read_text(encoding="utf-8-sig"))
            except Exception:
                suggestions = []
        return {
            "ok": True,
            "active_workspace": state.get("active_workspace"),
            "workspace_count": len(state.get("workspaces", {})),
            "workspaces": list(state.get("workspaces", {}).values())[:10],
            "memory_buckets": len(state.get("memory", {})),
            "suggestions_count": len(suggestions),
            "suggestions": suggestions[:5],
            "events": self._recent_events(10),
        }

