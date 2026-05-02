from __future__ import annotations

import argparse
from datetime import UTC, datetime
import json
from pathlib import Path
import shutil
import subprocess
import sys
from typing import Any

from evolving_ai.app.model_switchboard import build_model_router_payload

from .desktop_build import build_pyinstaller_command
from .profiles import aris_demo_profiles


REQUIRED_REPO_ASSETS = (
    "pyproject.toml",
    "evolving_ai/aris_demo/desktop.py",
    "evolving_ai/aris_demo/desktop_app.py",
    "evolving_ai/aris_demo/desktop_build.py",
    "evolving_ai/aris_demo/desktop_support.py",
    "evolving_ai/aris_demo/profiles.py",
)


def default_shipping_release_root(repo_root: Path) -> Path:
    return (Path(repo_root).resolve().parents[1] / "dist").resolve()


def _now_stamp() -> str:
    return datetime.now(UTC).strftime("%Y%m%d-%H%M%S")


def _entrypoint_name(artifact_name: str) -> str:
    return f"{artifact_name}.exe" if sys.platform.startswith("win") else artifact_name


def _json_payload(raw_text: str) -> dict[str, Any]:
    text = str(raw_text or "").strip()
    if not text:
        return {}
    try:
        payload = json.loads(text)
    except json.JSONDecodeError:
        return {}
    return payload if isinstance(payload, dict) else {}


def _run_command(command: list[str], *, cwd: Path) -> dict[str, Any]:
    completed = subprocess.run(
        command,
        cwd=cwd,
        capture_output=True,
        text=True,
        check=False,
    )
    return {
        "command": list(command),
        "returncode": completed.returncode,
        "stdout": completed.stdout.strip(),
        "stderr": completed.stderr.strip(),
        "ok": completed.returncode == 0,
    }


def shipping_precheck(
    *,
    repo_root: Path,
    python_executable: Path | None = None,
) -> dict[str, Any]:
    resolved_repo_root = Path(repo_root).resolve()
    resolved_python = Path(python_executable or sys.executable).resolve()
    required_items: list[dict[str, str]] = []
    for relative_path in REQUIRED_REPO_ASSETS:
        required_items.append(
            {
                "kind": "repo_asset",
                "label": relative_path,
                "path": str((resolved_repo_root / relative_path).resolve()),
            }
        )
    for profile in aris_demo_profiles():
        required_items.append(
            {
                "kind": "entry_point",
                "label": f"{profile.id}:{profile.entry_script}",
                "path": str((resolved_repo_root / "evolving_ai" / "aris_demo" / profile.entry_script).resolve()),
            }
        )

    missing_items = [
        item["path"]
        for item in required_items
        if not Path(item["path"]).exists()
    ]
    if not resolved_python.exists():
        missing_items.append(str(resolved_python))

    import_check = _run_command(
        [
            str(resolved_python),
            "-c",
            "import PyInstaller, PySide6, tkinter; print('shipping-precheck-ok')",
        ],
        cwd=resolved_repo_root,
    ) if resolved_python.exists() else {
        "command": [str(resolved_python)],
        "returncode": 1,
        "stdout": "",
        "stderr": "Python executable is missing.",
        "ok": False,
    }
    if not import_check["ok"]:
        missing_items.append("Python shipping dependencies: PyInstaller, PySide6, tkinter")

    return {
        "ok": not missing_items and bool(import_check["ok"]),
        "repo_root": str(resolved_repo_root),
        "python_executable": str(resolved_python),
        "required_items": required_items,
        "missing_items": missing_items,
        "dependency_check": import_check,
    }


def ship_release(
    *,
    repo_root: Path,
    python_executable: Path | None = None,
    release_root: Path | None = None,
    build_tag: str | None = None,
) -> dict[str, Any]:
    resolved_repo_root = Path(repo_root).resolve()
    resolved_python = Path(python_executable or sys.executable).resolve()
    resolved_release_root = Path(release_root or default_shipping_release_root(resolved_repo_root)).resolve()
    shipping_tag = str(build_tag or _now_stamp()).strip() or _now_stamp()

    precheck = shipping_precheck(
        repo_root=resolved_repo_root,
        python_executable=resolved_python,
    )
    artifacts: list[dict[str, Any]] = []
    manifest_payload: dict[str, Any] = {
        "ok": False,
        "lane": "shipping",
        "build_lane": "desktop_build",
        "build_tag": shipping_tag,
        "repo_root": str(resolved_repo_root),
        "release_root": str(resolved_release_root),
        "python_executable": str(resolved_python),
        "precheck": precheck,
        "verification_status": {
            "precheck": bool(precheck["ok"]),
            "source": False,
            "packaged": False,
        },
        "model_router": build_model_router_payload(),
        "artifacts": artifacts,
        "missing_items": list(precheck["missing_items"]),
        "generated_artifact_paths": [],
    }

    if not precheck["ok"]:
        return manifest_payload

    source_verifications: list[dict[str, Any]] = []
    for profile in aris_demo_profiles():
        verify_result = _run_command(
            [
                str(resolved_python),
                "-m",
                "evolving_ai.aris_demo.desktop",
                "--profile",
                profile.id,
                "--headless-smokecheck",
                "--no-workers",
            ],
            cwd=resolved_repo_root,
        )
        verify_result["profile_id"] = profile.id
        verify_result["artifact_name"] = profile.artifact_name
        verify_result["payload"] = _json_payload(str(verify_result.get("stdout", "")))
        source_verifications.append(verify_result)

    manifest_payload["verification_status"]["source"] = all(
        bool(item.get("ok")) for item in source_verifications
    )
    for item in source_verifications:
        if not item["ok"]:
            manifest_payload["missing_items"].append(f"source_verify:{item['profile_id']}")
    if not manifest_payload["verification_status"]["source"]:
        manifest_payload["source_verifications"] = source_verifications
        return manifest_payload

    build_root = (resolved_repo_root / ".runtime" / "shipping_lane" / shipping_tag).resolve()
    build_dist = (build_root / "dist").resolve()
    build_work = (build_root / "work").resolve()
    build_spec = (build_root / "spec").resolve()
    build_dist.mkdir(parents=True, exist_ok=True)
    build_work.mkdir(parents=True, exist_ok=True)
    build_spec.mkdir(parents=True, exist_ok=True)
    resolved_release_root.mkdir(parents=True, exist_ok=True)

    for profile in aris_demo_profiles():
        build_result = _run_command(
            build_pyinstaller_command(
                profile_id=profile.id,
                python_executable=str(resolved_python),
                distpath=build_dist,
                workpath=build_work,
                specpath=build_spec,
            ),
            cwd=resolved_repo_root,
        )
        built_folder = (build_dist / profile.artifact_name).resolve()
        release_folder = (resolved_release_root / profile.artifact_name).resolve()
        zip_base = (resolved_release_root / profile.artifact_name).resolve()
        zip_path = zip_base.with_suffix(".zip")
        entry_point = (release_folder / _entrypoint_name(profile.artifact_name)).resolve()
        internal_dir = (release_folder / "_internal").resolve()

        artifact_payload: dict[str, Any] = {
            "profile_id": profile.id,
            "profile": profile.payload(),
            "artifact_name": profile.artifact_name,
            "model_router": build_model_router_payload(),
            "build": build_result,
            "release_folder": str(release_folder),
            "zip_path": str(zip_path),
            "entry_point": str(entry_point),
            "internal_dir": str(internal_dir),
            "source_verification": next(
                (item for item in source_verifications if item["profile_id"] == profile.id),
                {},
            ),
            "missing_items": [],
            "verification": {},
        }

        if not build_result["ok"]:
            artifact_payload["missing_items"].append(f"build_failed:{profile.artifact_name}")
            artifacts.append(artifact_payload)
            manifest_payload["missing_items"].append(f"build_failed:{profile.artifact_name}")
            continue

        if release_folder.exists():
            shutil.rmtree(release_folder)
        shutil.copytree(built_folder, release_folder)
        if zip_path.exists():
            zip_path.unlink()

        if not release_folder.exists():
            artifact_payload["missing_items"].append(str(release_folder))
        if not entry_point.exists():
            artifact_payload["missing_items"].append(str(entry_point))
        if not internal_dir.exists():
            artifact_payload["missing_items"].append(str(internal_dir))

        if not artifact_payload["missing_items"]:
            shutil.make_archive(
                base_name=str(zip_base),
                format="zip",
                root_dir=resolved_release_root,
                base_dir=profile.artifact_name,
            )
            packaged_verify = _run_command(
                [str(entry_point), "--headless-smokecheck", "--no-workers"],
                cwd=release_folder,
            )
            packaged_verify["payload"] = _json_payload(str(packaged_verify.get("stdout", "")))
            artifact_payload["verification"] = {
                "structure_ok": True,
                "zip_exists": zip_path.exists(),
                "packaged_launch": packaged_verify,
            }
            if not zip_path.exists():
                artifact_payload["missing_items"].append(str(zip_path))
            if not packaged_verify["ok"]:
                artifact_payload["missing_items"].append(f"packaged_verify:{profile.artifact_name}")
        else:
            artifact_payload["verification"] = {
                "structure_ok": False,
                "zip_exists": False,
                "packaged_launch": {
                    "ok": False,
                    "returncode": 1,
                    "stdout": "",
                    "stderr": "Release structure is incomplete.",
                },
            }

        artifacts.append(artifact_payload)
        manifest_payload["generated_artifact_paths"].append(str(release_folder))
        if zip_path.exists():
            manifest_payload["generated_artifact_paths"].append(str(zip_path))
        manifest_payload["missing_items"].extend(artifact_payload["missing_items"])

    manifest_payload["source_verifications"] = source_verifications
    manifest_payload["verification_status"]["packaged"] = all(
        bool(item.get("verification", {}).get("packaged_launch", {}).get("ok"))
        and bool(item.get("verification", {}).get("zip_exists"))
        and not item.get("missing_items")
        for item in artifacts
    )
    manifest_payload["ok"] = (
        bool(precheck["ok"])
        and bool(manifest_payload["verification_status"]["source"])
        and bool(manifest_payload["verification_status"]["packaged"])
        and not manifest_payload["missing_items"]
    )

    manifest_path = (resolved_release_root / "release-manifest.json").resolve()
    manifest_payload["manifest_path"] = str(manifest_path)
    manifest_payload["generated_artifact_paths"].append(str(manifest_path))
    manifest_payload["missing_items"] = sorted({str(item) for item in manifest_payload["missing_items"] if str(item).strip()})
    manifest_path.write_text(
        json.dumps(manifest_payload, indent=2, ensure_ascii=True),
        encoding="utf-8",
    )
    return manifest_payload


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Run the ARIS Shipping Lane and emit a structured release readout.")
    parser.add_argument("--repo-root", type=Path, default=Path(__file__).resolve().parents[2])
    parser.add_argument("--python", type=Path, default=None, help="Python interpreter to use for verify/build steps.")
    parser.add_argument("--release-root", type=Path, default=None, help="Override the shipping release root.")
    parser.add_argument("--build-tag", default=None, help="Optional shipping tag used for build staging.")
    parser.add_argument(
        "--precheck-only",
        action="store_true",
        help="Run shipping precheck only and print the structured readout.",
    )
    args = parser.parse_args(argv)

    if args.precheck_only:
        payload = shipping_precheck(repo_root=args.repo_root, python_executable=args.python)
        print(json.dumps(payload, indent=2))
        return 0 if payload.get("ok") else 1

    payload = ship_release(
        repo_root=args.repo_root,
        python_executable=args.python,
        release_root=args.release_root,
        build_tag=args.build_tag,
    )
    print(json.dumps(payload, indent=2))
    return 0 if payload.get("ok") else 1


if __name__ == "__main__":
    raise SystemExit(main())