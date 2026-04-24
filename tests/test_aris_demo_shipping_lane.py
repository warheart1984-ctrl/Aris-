from __future__ import annotations

import json
from pathlib import Path
import shutil
import unittest
from unittest.mock import patch
import uuid

from evolving_ai.aris_demo.profiles import resolve_profile
from evolving_ai.aris_demo.shipping_lane import _entrypoint_name, ship_release, shipping_precheck


REPO_ROOT = Path(__file__).resolve().parents[1]
TEST_RUNTIME_ROOT = REPO_ROOT / ".runtime" / "aris-demo-shipping-test"


def _case_root(prefix: str) -> Path:
    TEST_RUNTIME_ROOT.mkdir(parents=True, exist_ok=True)
    root = TEST_RUNTIME_ROOT / f"{prefix}-{uuid.uuid4().hex[:10]}"
    root.mkdir(parents=True, exist_ok=True)
    return root


class ArisDemoShippingLaneTests(unittest.TestCase):
    def test_precheck_reports_missing_assets(self) -> None:
        repo_root = _case_root("precheck")
        self.addCleanup(lambda: shutil.rmtree(repo_root, ignore_errors=True))
        payload = shipping_precheck(
            repo_root=repo_root,
            python_executable=repo_root / "missing-python.exe",
        )

        self.assertFalse(payload["ok"])
        self.assertTrue(payload["missing_items"])
        self.assertIn("pyproject.toml", "\n".join(payload["missing_items"]))

    def test_ship_release_writes_manifest_release_folders_and_zips(self) -> None:
        repo_root = _case_root("repo")
        release_root = _case_root("release")
        self.addCleanup(lambda: shutil.rmtree(repo_root, ignore_errors=True))
        self.addCleanup(lambda: shutil.rmtree(release_root, ignore_errors=True))

        def fake_build_command(*, profile_id: str, python_executable: str, distpath: Path, workpath: Path, specpath: Path):
            del python_executable, workpath, specpath
            return ["build-profile", profile_id, str(distpath)]

        def fake_run_command(command: list[str], *, cwd: Path):
            del cwd
            if command and command[0] == "build-profile":
                profile = resolve_profile(command[1])
                distpath = Path(command[2])
                artifact_root = distpath / profile.artifact_name
                (artifact_root / "_internal").mkdir(parents=True, exist_ok=True)
                (artifact_root / _entrypoint_name(profile.artifact_name)).write_text("stub", encoding="utf-8")
                return {"command": command, "returncode": 0, "stdout": "", "stderr": "", "ok": True}
            if "-m" in command and "evolving_ai.aris_demo.desktop" in command:
                profile_id = command[command.index("--profile") + 1]
                return {
                    "command": command,
                    "returncode": 0,
                    "stdout": json.dumps({"profile_id": profile_id}),
                    "stderr": "",
                    "ok": True,
                }
            if command and str(command[0]).endswith(".exe"):
                return {"command": command, "returncode": 0, "stdout": "", "stderr": "", "ok": True}
            return {"command": command, "returncode": 1, "stdout": "", "stderr": "unexpected", "ok": False}

        with patch("evolving_ai.aris_demo.shipping_lane.shipping_precheck") as precheck_mock, patch(
            "evolving_ai.aris_demo.shipping_lane.build_pyinstaller_command",
            side_effect=fake_build_command,
        ), patch("evolving_ai.aris_demo.shipping_lane._run_command", side_effect=fake_run_command):
            precheck_mock.return_value = {
                "ok": True,
                "repo_root": str(repo_root),
                "python_executable": str(repo_root / "python.exe"),
                "required_items": [],
                "missing_items": [],
                "dependency_check": {"ok": True},
            }
            payload = ship_release(
                repo_root=repo_root,
                python_executable=repo_root / "python.exe",
                release_root=release_root,
                build_tag="unit-test",
            )

        self.assertTrue(payload["ok"])
        self.assertEqual(payload["model_router"]["mode"], "auto")
        self.assertEqual(len(payload["model_router"]["systems"]), 3)
        manifest_path = Path(payload["manifest_path"])
        self.assertTrue(manifest_path.exists())
        for profile_id in ("demo", "v1", "v2"):
            profile = resolve_profile(profile_id)
            artifact_root = release_root / profile.artifact_name
            zip_path = release_root / f"{profile.artifact_name}.zip"
            self.assertTrue(artifact_root.is_dir())
            self.assertTrue((artifact_root / "_internal").is_dir())
            self.assertTrue((artifact_root / _entrypoint_name(profile.artifact_name)).exists())
            self.assertTrue(zip_path.exists())

        manifest_payload = json.loads(manifest_path.read_text(encoding="utf-8"))
        self.assertTrue(manifest_payload["ok"])
        self.assertEqual(manifest_payload["model_router"]["mode"], "auto")
        self.assertEqual(len(manifest_payload["artifacts"]), 3)
        self.assertTrue(all("model_router" in item for item in manifest_payload["artifacts"]))
        self.assertTrue(all("profile" in item for item in manifest_payload["artifacts"]))
        self.assertIn(str(manifest_path), manifest_payload["generated_artifact_paths"])


if __name__ == "__main__":
    unittest.main()
