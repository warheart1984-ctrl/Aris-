from __future__ import annotations

import argparse
from dataclasses import asdict
import json
from pathlib import Path
import sys

try:
    from .profiles import DEFAULT_PROFILE_ID, profile_choices, resolve_profile
    from .desktop_support import ArisRuntimeDesktopHost
except ImportError:
    from evolving_ai.aris_runtime.profiles import DEFAULT_PROFILE_ID, profile_choices, resolve_profile
    from evolving_ai.aris_runtime.desktop_support import ArisRuntimeDesktopHost


def _smokecheck_payload(host: ArisRuntimeDesktopHost) -> dict[str, object]:
    session_id = host.ensure_session(title_seed=f"{host.profile.desktop_title} Smokecheck")
    snapshot = host.snapshot(session_id=session_id)
    return {
        "session_id": session_id,
        "data_root": str(host.data_root),
        "profile_id": host.profile.id,
        "system_name": snapshot.status.get("system_name", host.profile.system_name),
        "law_mode": snapshot.status.get("law_mode", "unknown"),
        "feature_count": len(snapshot.features),
        "packaging_targets": [item.id for item in snapshot.packaging_targets],
        "packaging_artifacts": [item.artifact for item in snapshot.packaging_targets],
        "model_router": snapshot.status.get("model_router", snapshot.config.get("model_router", {})),
        "ul_runtime_present": bool(snapshot.status.get("ul_runtime")),
        "runtime_mode": snapshot.status.get("runtime_mode", snapshot.status.get("demo_mode", {})),
    }


def main(argv: list[str] | None = None, *, default_profile: str = DEFAULT_PROFILE_ID) -> int:
    parser = argparse.ArgumentParser(description="Launch the ARIS V2 desktop host.")
    parser.add_argument("--data-root", type=Path, default=None, help="Override the desktop data root.")
    parser.add_argument(
        "--profile",
        choices=profile_choices(),
        default=resolve_profile(default_profile).id,
        help="Select the ARIS desktop profile to launch.",
    )
    parser.add_argument(
        "--headless-smokecheck",
        action="store_true",
        help="Instantiate the desktop host and print a JSON smokecheck payload without opening a window.",
    )
    parser.add_argument(
        "--print-build-targets",
        action="store_true",
        help="Print native build targets without launching the window.",
    )
    parser.add_argument(
        "--no-workers",
        action="store_true",
        help="Disable background worker startup for smokechecks or scripted inspection.",
    )
    args = parser.parse_args(argv)
    profile = resolve_profile(args.profile)

    host = ArisRuntimeDesktopHost(
        data_root=args.data_root,
        start_workers=not args.no_workers,
        profile_id=profile.id,
    )
    try:
        if args.print_build_targets:
            print(
                json.dumps(
                    [asdict(item) for item in host.snapshot().packaging_targets],
                    indent=2,
                )
            )
            return 0

        if args.headless_smokecheck:
            print(json.dumps(_smokecheck_payload(host), indent=2))
            return 0

        try:
            from .desktop_app import launch_desktop_app
        except ImportError:
            try:
                from evolving_ai.aris_runtime.desktop_app import launch_desktop_app
            except ImportError as exc:
                message = (
                    f"{profile.desktop_title} could not load. "
                    "The desktop app runtime is missing or PySide6 is unavailable."
                )
                print(message, file=sys.stderr)
                raise SystemExit(1) from exc
        return int(launch_desktop_app(host))
    finally:
        host.close()


if __name__ == "__main__":
    raise SystemExit(main())
