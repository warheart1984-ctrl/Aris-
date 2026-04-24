from __future__ import annotations

from pathlib import Path
import shutil
import unittest
import uuid

from evolving_ai.aris_demo.desktop_build import build_pyinstaller_command
from evolving_ai.aris_demo.desktop_runtime import ULDesktopRuntimeBootstrap, default_runtime_root


REPO_ROOT = Path(__file__).resolve().parents[1]
TEST_RUNTIME_ROOT = REPO_ROOT / ".runtime" / "aris-demo-desktop-runtime-test"


def _make_bootstrap(*, include_build_tools: bool = False) -> tuple[ULDesktopRuntimeBootstrap, Path]:
    TEST_RUNTIME_ROOT.mkdir(parents=True, exist_ok=True)
    root = TEST_RUNTIME_ROOT / f"case-{uuid.uuid4().hex[:10]}"
    bootstrap = ULDesktopRuntimeBootstrap(
        repo_root=REPO_ROOT,
        runtime_root=root,
        include_build_tools=include_build_tools,
    )
    return bootstrap, root


class ArisDemoDesktopRuntimeTests(unittest.TestCase):
    def test_default_runtime_root_uses_runtime_folder(self) -> None:
        root = default_runtime_root(REPO_ROOT)

        self.assertEqual(root, (REPO_ROOT / ".runtime" / "ul_desktop_runtime").resolve())

    def test_manifest_is_bound_to_ul_runtime(self) -> None:
        bootstrap, root = _make_bootstrap(include_build_tools=True)
        self.addCleanup(lambda: shutil.rmtree(root, ignore_errors=True))

        manifest = bootstrap.build_manifest()

        self.assertEqual(manifest.runtime_name, "ARIS Demo UL Desktop Runtime")
        self.assertEqual(manifest.identity_source, "UL")
        self.assertEqual(manifest.governance_model, "CISIV")
        self.assertEqual(manifest.binding_layer, "Universal Adapter Protocol")
        self.assertEqual(manifest.speech_chain, ("0001", "1000", "1001"))
        self.assertIn("desktop-build", manifest.install_extras)
        self.assertIn("PySide6.QtWidgets", manifest.desktop_modules)
        self.assertEqual(manifest.model_router_mode, "auto")
        self.assertIn("General: gemma3:12b", manifest.model_systems)
        self.assertIn("Coding: devstral", manifest.model_systems)
        self.assertIn("Light Coding: qwen2.5-coder:7b", manifest.model_systems)
        self.assertEqual(manifest.profile_ids, ("demo", "v1", "v2"))
        self.assertIn("ARIS Demo V2", manifest.profile_artifacts)
        self.assertTrue(manifest.manifest_hash)

    def test_plan_payload_emits_prepare_and_run_commands(self) -> None:
        bootstrap, root = _make_bootstrap(include_build_tools=True)
        self.addCleanup(lambda: shutil.rmtree(root, ignore_errors=True))

        payload = bootstrap.plan_payload()
        commands = payload["commands"]

        self.assertIn("-m", commands["create_venv"])
        self.assertIn("venv", commands["create_venv"])
        self.assertIn("desktop-build", " ".join(commands["install_runtime"]))
        self.assertEqual(commands["run_desktop"][-2:], ["-m", "evolving_ai.aris_demo.desktop"])
        self.assertIn("PyInstaller", commands["build_desktop"])

    def test_build_command_can_target_runtime_python(self) -> None:
        command = build_pyinstaller_command(python_executable="C:/runtime/python.exe")

        self.assertEqual(command[0], "C:/runtime/python.exe")
        self.assertIn("PySide6.QtCore", command)


if __name__ == "__main__":
    unittest.main()
