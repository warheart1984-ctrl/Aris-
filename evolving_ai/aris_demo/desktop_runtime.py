from __future__ import annotations

import argparse
from dataclasses import dataclass
import hashlib
import importlib.util
import json
from pathlib import Path
import site
import subprocess
import sys
from typing import Any

from src.ul_runtime import ULRuntimeSubstrate

from .desktop_build import build_pyinstaller_command
from .profiles import aris_demo_profiles
from evolving_ai.app.model_switchboard import build_model_router_payload


def _no_observation_block(_path: str) -> bool:
    return False


def default_runtime_root(repo_root: Path) -> Path:
    return (Path(repo_root).resolve() / ".runtime" / "ul_desktop_runtime").resolve()


def _venv_python_path(venv_root: Path) -> Path:
    if sys.platform.startswith("win"):
        return (venv_root / "Scripts" / "python.exe").resolve()
    return (venv_root / "bin" / "python").resolve()


def _user_virtualenv_script() -> Path | None:
    user_site = Path(site.getusersitepackages())
    scripts_root = user_site.parent / ("Scripts" if sys.platform.startswith("win") else "bin")
    script_name = "virtualenv.exe" if sys.platform.startswith("win") else "virtualenv"
    script_path = (scripts_root / script_name).resolve()
    return script_path if script_path.exists() else None


@dataclass(frozen=True, slots=True)
class ULDesktopRuntimeManifest:
    runtime_name: str
    runtime_root: str
    venv_root: str
    python_executable: str
    identity_source: str
    governance_model: str
    binding_layer: str
    speech_chain: tuple[str, ...]
    foundation_entries: tuple[str, ...]
    desktop_modules: tuple[str, ...]
    install_extras: tuple[str, ...]
    launch_module: str
    build_module: str
    pyinstaller_artifact: str
    profile_ids: tuple[str, ...]
    profile_artifacts: tuple[str, ...]
    model_router_mode: str
    model_systems: tuple[str, ...]
    manifest_hash: str

    def payload(self) -> dict[str, Any]:
        return {
            "runtime_name": self.runtime_name,
            "runtime_root": self.runtime_root,
            "venv_root": self.venv_root,
            "python_executable": self.python_executable,
            "identity_source": self.identity_source,
            "governance_model": self.governance_model,
            "binding_layer": self.binding_layer,
            "speech_chain": list(self.speech_chain),
            "foundation_entries": list(self.foundation_entries),
            "desktop_modules": list(self.desktop_modules),
            "install_extras": list(self.install_extras),
            "launch_module": self.launch_module,
            "build_module": self.build_module,
            "pyinstaller_artifact": self.pyinstaller_artifact,
            "profile_ids": list(self.profile_ids),
            "profile_artifacts": list(self.profile_artifacts),
            "model_router_mode": self.model_router_mode,
            "model_systems": list(self.model_systems),
            "manifest_hash": self.manifest_hash,
        }


class ULDesktopRuntimeBootstrap:
    def __init__(
        self,
        *,
        repo_root: Path,
        runtime_root: Path | None = None,
        base_python: Path | None = None,
        include_build_tools: bool = False,
    ) -> None:
        self.repo_root = Path(repo_root).resolve()
        self.runtime_root = Path(runtime_root or default_runtime_root(self.repo_root)).resolve()
        self.venv_root = (self.runtime_root / "venv").resolve()
        self.base_python = Path(base_python or sys.executable).resolve()
        self.include_build_tools = include_build_tools
        self.ul_runtime_root = (self.runtime_root / "ul").resolve()
        self.substrate = ULRuntimeSubstrate(
            runtime_root=self.ul_runtime_root,
            observation_blocked=_no_observation_block,
        )

    @property
    def runtime_python(self) -> Path:
        return _venv_python_path(self.venv_root)

    @property
    def install_extras(self) -> tuple[str, ...]:
        return ("desktop-build",) if self.include_build_tools else ("desktop",)

    @property
    def manifest_path(self) -> Path:
        return (self.runtime_root / "ul_desktop_runtime_manifest.json").resolve()

    def install_spec(self) -> str:
        extras = ",".join(self.install_extras)
        return f".[{extras}]"

    def build_manifest(self) -> ULDesktopRuntimeManifest:
        inventory = self.substrate.primitive_inventory()
        substrate_payload = self.substrate.status_payload()
        model_router = build_model_router_payload()
        model_systems = tuple(
            f"{str(item.get('label', item.get('id', 'system'))).strip()}: {str(item.get('model', 'unknown')).strip()}"
            for item in list(model_router.get("systems", []))
            if isinstance(item, dict)
        )
        profiles = aris_demo_profiles()
        canonical_payload = {
            "runtime_name": "ARIS Demo UL Desktop Runtime",
            "runtime_root": str(self.runtime_root),
            "venv_root": str(self.venv_root),
            "python_executable": str(self.runtime_python),
            "identity_source": inventory.identity_source,
            "governance_model": inventory.governance_model,
            "binding_layer": inventory.binding_layer,
            "speech_chain": list(inventory.speech_chain),
            "foundation_entries": list(substrate_payload.get("foundation_entries", [])),
            "desktop_modules": [
                "PySide6.QtCore",
                "PySide6.QtGui",
                "PySide6.QtWidgets",
                "uvicorn",
                "fastapi",
            ],
            "install_extras": list(self.install_extras),
            "launch_module": "evolving_ai.aris_demo.desktop",
            "build_module": "evolving_ai.aris_demo.desktop_build",
            "pyinstaller_artifact": "ARIS Demo.exe" if sys.platform.startswith("win") else "ARIS Demo",
            "profile_ids": [profile.id for profile in profiles],
            "profile_artifacts": [profile.artifact_name for profile in profiles],
            "model_router_mode": str(model_router.get("mode", "auto")),
            "model_systems": list(model_systems),
        }
        manifest_hash = hashlib.sha256(
            json.dumps(canonical_payload, sort_keys=True, ensure_ascii=True).encode("utf-8")
        ).hexdigest()
        return ULDesktopRuntimeManifest(
            runtime_name=str(canonical_payload["runtime_name"]),
            runtime_root=str(canonical_payload["runtime_root"]),
            venv_root=str(canonical_payload["venv_root"]),
            python_executable=str(canonical_payload["python_executable"]),
            identity_source=str(canonical_payload["identity_source"]),
            governance_model=str(canonical_payload["governance_model"]),
            binding_layer=str(canonical_payload["binding_layer"]),
            speech_chain=tuple(canonical_payload["speech_chain"]),
            foundation_entries=tuple(canonical_payload["foundation_entries"]),
            desktop_modules=tuple(canonical_payload["desktop_modules"]),
            install_extras=tuple(canonical_payload["install_extras"]),
            launch_module=str(canonical_payload["launch_module"]),
            build_module=str(canonical_payload["build_module"]),
            pyinstaller_artifact=str(canonical_payload["pyinstaller_artifact"]),
            profile_ids=tuple(canonical_payload["profile_ids"]),
            profile_artifacts=tuple(canonical_payload["profile_artifacts"]),
            model_router_mode=str(canonical_payload["model_router_mode"]),
            model_systems=tuple(canonical_payload["model_systems"]),
            manifest_hash=manifest_hash,
        )

    def write_manifest(self) -> dict[str, Any]:
        self.runtime_root.mkdir(parents=True, exist_ok=True)
        manifest = self.build_manifest()
        self.manifest_path.write_text(
            json.dumps(manifest.payload(), indent=2, ensure_ascii=True),
            encoding="utf-8",
        )
        return manifest.payload()

    def runtime_commands(self) -> dict[str, Any]:
        runtime_python = str(self.runtime_python)
        build_command = build_pyinstaller_command(python_executable=runtime_python)
        return {
            "create_venv": [str(self.base_python), "-m", "venv", str(self.venv_root)],
            "create_venv_virtualenv": [str(self.base_python), "-m", "virtualenv", str(self.venv_root)],
            "create_venv_virtualenv_script": (
                [str(_user_virtualenv_script()), str(self.venv_root)]
                if _user_virtualenv_script() is not None
                else []
            ),
            "upgrade_pip": [runtime_python, "-m", "pip", "install", "--upgrade", "pip", "setuptools", "wheel"],
            "install_runtime": [runtime_python, "-m", "pip", "install", "-e", self.install_spec()],
            "verify_imports": [
                runtime_python,
                "-c",
                "import PySide6, fastapi, uvicorn; print('desktop-runtime-ok')",
            ],
            "smokecheck": [
                runtime_python,
                "-m",
                "evolving_ai.aris_demo.desktop",
                "--headless-smokecheck",
                "--no-workers",
            ],
            "run_desktop": [runtime_python, "-m", "evolving_ai.aris_demo.desktop"],
            "build_desktop": build_command,
        }

    def plan_payload(self) -> dict[str, Any]:
        manifest = self.build_manifest()
        return {
            "runtime": manifest.payload(),
            "commands": self.runtime_commands(),
            "runtime_exists": self.runtime_python.exists(),
            "ul_runtime": self.substrate.status_payload(),
        }

    def _base_python_has_virtualenv(self) -> bool:
        return importlib.util.find_spec("virtualenv") is not None or _user_virtualenv_script() is not None

    def verify_runtime(self) -> dict[str, Any]:
        manifest = self.write_manifest()
        payload: dict[str, Any] = {
            "ok": False,
            "runtime": manifest,
            "runtime_python_exists": self.runtime_python.exists(),
            "imports_ok": False,
            "smokecheck_ok": False,
        }
        if not self.runtime_python.exists():
            payload["error"] = "Runtime python does not exist yet."
            return payload

        import_result = subprocess.run(
            self.runtime_commands()["verify_imports"],
            cwd=self.repo_root,
            capture_output=True,
            text=True,
        )
        payload["imports_ok"] = import_result.returncode == 0
        payload["imports_stdout"] = import_result.stdout.strip()
        payload["imports_stderr"] = import_result.stderr.strip()
        if import_result.returncode != 0:
            payload["error"] = "Desktop runtime import verification failed."
            return payload

        smoke_result = subprocess.run(
            self.runtime_commands()["smokecheck"],
            cwd=self.repo_root,
            capture_output=True,
            text=True,
        )
        payload["smokecheck_ok"] = smoke_result.returncode == 0
        payload["smokecheck_stdout"] = smoke_result.stdout.strip()
        payload["smokecheck_stderr"] = smoke_result.stderr.strip()
        if smoke_result.returncode != 0:
            payload["error"] = "Desktop runtime smokecheck failed."
            return payload

        payload["ok"] = True
        return payload

    def prepare_runtime(self) -> dict[str, Any]:
        self.runtime_root.mkdir(parents=True, exist_ok=True)
        commands = self.runtime_commands()
        results: list[dict[str, Any]] = []
        create_steps = ["create_venv"]
        completed = subprocess.run(
            commands["create_venv"],
            cwd=self.repo_root,
            capture_output=True,
            text=True,
            check=False,
        )
        results.append(
            {
                "step": "create_venv",
                "command": commands["create_venv"],
                "returncode": completed.returncode,
                "stdout": completed.stdout.strip(),
                "stderr": completed.stderr.strip(),
            }
        )
        if completed.returncode != 0 and self._base_python_has_virtualenv():
            fallback_command = (
                commands["create_venv_virtualenv_script"]
                if commands["create_venv_virtualenv_script"]
                else commands["create_venv_virtualenv"]
            )
            fallback = subprocess.run(
                fallback_command,
                cwd=self.repo_root,
                capture_output=True,
                text=True,
                check=False,
            )
            results.append(
                {
                    "step": "create_venv_virtualenv",
                    "command": fallback_command,
                    "returncode": fallback.returncode,
                    "stdout": fallback.stdout.strip(),
                    "stderr": fallback.stderr.strip(),
                }
            )
            completed = fallback
        if completed.returncode != 0:
            manifest = self.write_manifest()
            return {
                "ok": False,
                "runtime": manifest,
                "results": results,
                "error": "create_venv failed",
            }

        for key in ("upgrade_pip", "install_runtime"):
            command = commands[key]
            completed = subprocess.run(
                command,
                cwd=self.repo_root,
                capture_output=True,
                text=True,
                check=False,
            )
            results.append(
                {
                    "step": key,
                    "command": command,
                    "returncode": completed.returncode,
                    "stdout": completed.stdout.strip(),
                    "stderr": completed.stderr.strip(),
                }
            )
            if completed.returncode != 0:
                manifest = self.write_manifest()
                return {
                    "ok": False,
                    "runtime": manifest,
                    "results": results,
                    "error": f"{key} failed",
                }
        verification = self.verify_runtime()
        verification["results"] = results
        return verification


def _default_repo_root() -> Path:
    return Path(__file__).resolve().parents[2]


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Build and verify the UL-bound PySide6 desktop runtime for ARIS Demo.")
    parser.add_argument("--runtime-root", type=Path, default=None, help="Override the UL desktop runtime root.")
    parser.add_argument("--python", type=Path, default=None, help="Override the base Python executable used to create the runtime.")
    parser.add_argument(
        "--with-build-tools",
        action="store_true",
        help="Install PyInstaller into the UL desktop runtime as part of preparation.",
    )
    parser.add_argument(
        "--print-plan",
        action="store_true",
        help="Print the UL desktop runtime manifest and required commands without creating it.",
    )
    parser.add_argument(
        "--prepare",
        action="store_true",
        help="Create the UL desktop runtime venv, install desktop dependencies, and verify imports plus smokecheck.",
    )
    parser.add_argument(
        "--verify",
        action="store_true",
        help="Verify an existing UL desktop runtime without reinstalling it.",
    )
    parser.add_argument(
        "--print-run-command",
        action="store_true",
        help="Print the canonical command that launches the desktop from the UL runtime.",
    )
    parser.add_argument(
        "--print-build-command",
        action="store_true",
        help="Print the canonical PyInstaller command that builds the desktop from the UL runtime.",
    )
    args = parser.parse_args(argv)

    bootstrap = ULDesktopRuntimeBootstrap(
        repo_root=_default_repo_root(),
        runtime_root=args.runtime_root,
        base_python=args.python,
        include_build_tools=args.with_build_tools,
    )

    if args.print_run_command:
        print(json.dumps({"command": bootstrap.runtime_commands()["run_desktop"]}, indent=2))
        return 0
    if args.print_build_command:
        print(json.dumps({"command": bootstrap.runtime_commands()["build_desktop"]}, indent=2))
        return 0
    if args.verify:
        payload = bootstrap.verify_runtime()
        print(json.dumps(payload, indent=2))
        return 0 if payload.get("ok") else 1
    if args.prepare:
        payload = bootstrap.prepare_runtime()
        print(json.dumps(payload, indent=2))
        return 0 if payload.get("ok") else 1

    print(json.dumps(bootstrap.plan_payload(), indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
