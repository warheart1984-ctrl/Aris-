from __future__ import annotations

from pathlib import Path

from evolving_ai.app.service import ChatService
from evolving_ai.aris.service import ArisChatService, GovernedExecutor

from .profiles import DEFAULT_PROFILE_ID, resolve_profile
from .runtime import build_runtime_for_profile


class ArisDemoChatService(ArisChatService):
    def __init__(self, config, *, profile_id: str = DEFAULT_PROFILE_ID) -> None:
        ChatService.__init__(self, config)
        profile = resolve_profile(profile_id)
        repo_root = Path(__file__).resolve().parents[2]
        runtime_root = self.config.workspaces_dir.parent / profile.runtime_dir_name
        self.profile = profile
        self.aris = build_runtime_for_profile(
            profile_id=profile.id,
            repo_root=repo_root,
            runtime_root=runtime_root,
        )
        self.executor = GovernedExecutor(self.executor, self.aris)