from __future__ import annotations

import unittest

from evolving_ai.aris_runtime.workspace_logic import (
    BRAIN_TARGET_OPTIONS,
    build_workspace_decision,
    route_for_target,
    seed_workspace_messages,
    workspace_status_pills,
)


class ArisRuntimeWorkspaceLogicTests(unittest.TestCase):
    def test_target_options_exclude_evolving_core(self) -> None:
        target_block = " ".join(BRAIN_TARGET_OPTIONS)

        self.assertIn("Forge", BRAIN_TARGET_OPTIONS)
        self.assertIn("ForgeEval", BRAIN_TARGET_OPTIONS)
        self.assertNotIn("Evolving Core", target_block)
        self.assertNotIn("Evolving Engine", target_block)

    def test_protected_request_is_blocked_with_allowed_alternatives(self) -> None:
        decision = build_workspace_decision(
            prompt="Route this through the evolving core and self-rewrite the runtime.",
            brain_state={
                "mode": "Route",
                "scope": "Workspace",
                "target": "Forge",
                "permission": "Governed Workspace Mode",
                "response_style": "Operator",
            },
            repo={"name": "ARIS-runtime"},
            task={"id": "AR-145", "title": "Inspect protected execution boundaries", "status": "Review"},
        )

        self.assertTrue(decision["blocked"])
        self.assertIn("protected and unavailable", decision["content"])
        self.assertIn("Route To Forge", decision["suggestions"])
        self.assertIn("Evolving Core Locked", decision["pills"])

    def test_forge_route_keeps_aris_as_speaker(self) -> None:
        decision = build_workspace_decision(
            prompt="Prepare the selected task for Forge and hold it for approval.",
            brain_state={
                "mode": "Build",
                "scope": "Selected Task",
                "target": "Forge",
                "permission": "Approval Required",
                "response_style": "Operator",
            },
            repo={"name": "ARIS-runtime"},
            task={"id": "AR-118", "title": "Create task board with approvals", "status": "Review"},
        )

        self.assertFalse(decision["blocked"])
        self.assertEqual(decision["route"], ["Jarvis Blueprint", "Operator", "Forge", "Outcome"])
        self.assertIn("I have prepared the execution path", decision["content"])
        self.assertFalse(any(str(line).startswith("Forge:") for line in decision["worker_lines"]))
        self.assertEqual(decision["worker_title"], "Forge Route")

    def test_seed_messages_and_status_pills_keep_aris_identity(self) -> None:
        messages = seed_workspace_messages()
        pills = workspace_status_pills(
            {
                "mode": "Inspect",
                "scope": "Selected Repo",
                "target": "ARIS Only",
                "permission": "Read Only",
                "response_style": "Technical",
            }
        )

        self.assertEqual(messages[0]["role"], "assistant")
        self.assertIn("ARIS workspace is online", messages[0]["content"])
        self.assertFalse(any(message["content"].startswith("Forge:") for message in messages))
        self.assertEqual(route_for_target("ForgeEval"), ["Jarvis Blueprint", "Operator", "ForgeEval", "Outcome"])
        self.assertEqual(pills, ["Forge Available", "Approval Gated", "Evolving Core Locked"])


if __name__ == "__main__":
    unittest.main()
