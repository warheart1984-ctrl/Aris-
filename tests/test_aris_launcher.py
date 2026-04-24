from __future__ import annotations

import unittest

from evolving_ai.aris.launcher import _status_lines


class ArisLauncherTests(unittest.TestCase):
    def test_status_lines_include_model_router(self) -> None:
        lines = _status_lines(
            {
                "repo_target": "C:/workspace",
                "law_mode": "governed",
                "meta_law_1001_active": True,
                "model_router": {
                    "mode": "manual",
                    "pinned_system": "coding",
                    "systems": [
                        {"id": "general", "label": "General", "model": "gemma3:12b"},
                        {"id": "coding", "label": "Coding", "model": "devstral"},
                        {"id": "light_coding", "label": "Light Coding", "model": "qwen2.5-coder:7b"},
                    ],
                },
                "repo_logbook": {"active": True},
                "shield_of_truth": {"active": True},
                "mystic": {"active": True},
                "mystic_reflection": {"active": True, "merged_with_jarvis": True},
                "forge": {"connected": True},
                "forge_eval": {"connected": True},
                "hall_of_discard": {"active": True},
                "hall_of_shame": {"active": True},
                "hall_of_fame": {"active": True},
                "execution_backend": {"active_backend": "docker", "requested_backend": "auto"},
                "shell_execution": {"enabled": True, "degraded": False, "detail": "ready"},
                "kill_switch": {"mode": "nominal"},
                "startup_blockers": [],
            }
        )

        rendered = "\n".join(lines)
        self.assertIn("Model router: manual (coding)", rendered)
        self.assertIn("General: gemma3:12b", rendered)
        self.assertIn("Coding: devstral", rendered)
        self.assertIn("Light Coding: qwen2.5-coder:7b", rendered)


if __name__ == "__main__":
    unittest.main()
