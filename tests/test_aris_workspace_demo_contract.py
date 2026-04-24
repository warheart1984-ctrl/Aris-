from __future__ import annotations

from pathlib import Path
import re
import unittest


COMPONENT_PATH = Path(__file__).resolve().parents[1] / "prototypes" / "ArisWorkspaceDemo.jsx"


class ArisWorkspaceDemoContractTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.source = COMPONENT_PATH.read_text(encoding="utf-8")

    def test_target_options_allow_forge_but_not_evolving_core(self) -> None:
        match = re.search(r"const targetOptions = \[(.*?)\];", self.source, re.S)
        self.assertIsNotNone(match)
        target_block = match.group(1)

        for value in ["ARIS Only", "Forge", "ForgeEval", "Runtime", "Memory", "Operator Review"]:
            self.assertIn(f'"{value}"', target_block)

        self.assertNotIn("Evolving Core", target_block)
        self.assertNotIn("Evolving Engine", target_block)

    def test_brain_control_sets_are_present(self) -> None:
        for required in [
            "const modeOptions =",
            "const scopeOptions =",
            "const permissionOptions =",
            "const responseStyleOptions =",
            "Build repo connection manager",
            "Create task board with approvals",
            "Add branch and environment controls",
            "Expose Forge as worker status only",
            "Inspect protected execution boundaries",
        ]:
            self.assertIn(required, self.source)

    def test_protected_boundary_copy_is_present(self) -> None:
        self.assertIn("That path is protected and unavailable from this workspace.", self.source)
        self.assertIn("The evolving core is not exposed to ARIS in demo mode.", self.source)
        self.assertIn("I can continue through Forge, evaluation, approval flow, or standard workspace actions instead.", self.source)
        self.assertIn("Evolving Core Locked", self.source)

    def test_demo_route_examples_are_present(self) -> None:
        for route in [
            "Jarvis Blueprint\", \"Operator\", \"Forge\", \"Outcome",
            "Jarvis Blueprint\", \"Operator\", \"ForgeEval\", \"Outcome",
            "Jarvis Blueprint\", \"Operator\", \"Governance Review\", \"Outcome",
        ]:
            self.assertIn(route, self.source)


if __name__ == "__main__":
    unittest.main()
