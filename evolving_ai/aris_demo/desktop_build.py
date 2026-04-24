from __future__ import annotations

import argparse
import json
from pathlib import Path
import subprocess
import sys

from .profiles import DEFAULT_PROFILE_ID, aris_demo_profiles, profile_choices, resolve_profile
from .desktop_support import current_packaging_target, desktop_packaging_targets


def build_pyinstaller_command(
    *,
    profile_id: str = DEFAULT_PROFILE_ID,
    python_executable: str | None = None,
    distpath: Path | None = None,
    workpath: Path | None = None,
    specpath: Path | None = None,
) -> list[str]:
    profile = resolve_profile(profile_id)
    module_path = Path(__file__).with_name(profile.entry_script).resolve()
    command = [
        str(python_executable or sys.executable),
        "-m",
        "PyInstaller",
        "--noconfirm",
        "--windowed",
        "--name",
        profile.artifact_name,
        "--hidden-import",
        "PySide6.QtCore",
        "--hidden-import",
        "PySide6.QtGui",
        "--hidden-import",
        "PySide6.QtWidgets",
        "--hidden-import",
        "PySide6.QtMultimedia",
        "--hidden-import",
        "tkinter",
        "--hidden-import",
        "tkinter.filedialog",
        "--hidden-import",
        "pyttsx3",
    ]
    if distpath is not None:
        command.extend(["--distpath", str(distpath.resolve())])
    if workpath is not None:
        command.extend(["--workpath", str(workpath.resolve())])
    if specpath is not None:
        command.extend(["--specpath", str(specpath.resolve())])
    command.append(str(module_path))
    return command


def _profiles_payload() -> list[dict[str, str]]:
    return [
        {
            "id": profile.id,
            "label": profile.label,
            "system_name": profile.system_name,
            "artifact_name": profile.artifact_name,
            "entry_script": profile.entry_script,
            "runtime_dir_name": profile.runtime_dir_name,
        }
        for profile in aris_demo_profiles()
    ]


def _targets_payload(profile_id: str = DEFAULT_PROFILE_ID) -> list[dict[str, object]]:
    return [
        {
            "id": target.id,
            "label": target.label,
            "build_os": target.build_os,
            "artifact": target.artifact,
            "detail": target.detail,
            "profile_id": target.profile_id,
            "profile_label": target.profile_label,
            "model_router_mode": target.model_router_mode,
            "model_systems": list(target.model_systems),
        }
        for target in desktop_packaging_targets(profile_id=profile_id)
    ]


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Build or inspect native packaging targets for ARIS Demo Desktop.")
    parser.add_argument(
        "--variant",
        choices=profile_choices(),
        default=DEFAULT_PROFILE_ID,
        help="Select which ARIS Demo variant to build.",
    )
    parser.add_argument(
        "--print-profiles",
        action="store_true",
        help="Print the supported ARIS Demo desktop variants as JSON.",
    )
    parser.add_argument(
        "--print-targets",
        action="store_true",
        help="Print the native build targets for Windows, macOS, and Linux as JSON.",
    )
    parser.add_argument(
        "--print-command",
        action="store_true",
        help="Print the PyInstaller command for the current platform without running it.",
    )
    parser.add_argument(
        "--build-current",
        action="store_true",
        help="Run the PyInstaller build for the current platform.",
    )
    parser.add_argument(
        "--build-all-current",
        action="store_true",
        help="Run PyInstaller once for each supported ARIS Demo variant on the current platform.",
    )
    parser.add_argument("--distpath", type=Path, default=None, help="Optional PyInstaller dist path.")
    parser.add_argument("--workpath", type=Path, default=None, help="Optional PyInstaller work path.")
    parser.add_argument("--specpath", type=Path, default=None, help="Optional PyInstaller spec path.")
    args = parser.parse_args(argv)
    profile = resolve_profile(args.variant)

    if args.print_profiles:
        print(json.dumps(_profiles_payload(), indent=2))
        return 0
    if args.print_targets:
        print(json.dumps(_targets_payload(profile.id), indent=2))
        return 0

    command = build_pyinstaller_command(
        profile_id=profile.id,
        distpath=args.distpath,
        workpath=args.workpath,
        specpath=args.specpath,
    )
    if args.print_command or not (args.build_current or args.build_all_current):
        print(json.dumps(
            {
                "profiles": _profiles_payload(),
                "target": _targets_payload(profile.id),
                "selected_profile": {
                    "id": profile.id,
                    "label": profile.label,
                    "artifact_name": profile.artifact_name,
                    "entry_script": profile.entry_script,
                },
                "current_target": {
                    "id": current_packaging_target(profile_id=profile.id).id,
                    "label": current_packaging_target(profile_id=profile.id).label,
                    "artifact": current_packaging_target(profile_id=profile.id).artifact,
                    "detail": current_packaging_target(profile_id=profile.id).detail,
                    "profile_id": current_packaging_target(profile_id=profile.id).profile_id,
                    "model_router_mode": current_packaging_target(profile_id=profile.id).model_router_mode,
                    "model_systems": list(current_packaging_target(profile_id=profile.id).model_systems),
                },
                "command": command,
            },
            indent=2,
        ))
        return 0

    if args.build_all_current:
        for item in aris_demo_profiles():
            subprocess.run(
                build_pyinstaller_command(
                    profile_id=item.id,
                    distpath=args.distpath,
                    workpath=args.workpath,
                    specpath=args.specpath,
                ),
                check=True,
            )
        return 0

    subprocess.run(command, check=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
