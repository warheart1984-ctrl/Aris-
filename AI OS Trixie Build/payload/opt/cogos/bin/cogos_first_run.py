#!/usr/bin/env python3
"""CLI for CoGOS first-run wizard."""

from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path


ROOT = Path(os.environ.get("COGOS_ROOT", "/opt/cogos"))
RUNTIME = ROOT / "runtime"
if str(RUNTIME) not in sys.path:
    sys.path.insert(0, str(RUNTIME))

from first_run_wizard import FirstRunWizard  # noqa: E402


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="CoGOS first-run setup")
    sub = parser.add_subparsers(dest="cmd", required=True)
    sub.add_parser("status")
    apply = sub.add_parser("apply")
    apply.add_argument("--hostname", default="cogos")
    apply.add_argument("--profile-id", default="operator")
    apply.add_argument("--display-name", default="Operator")
    apply.add_argument("--mode", choices=["manual", "automatic"], default="manual")
    apply.add_argument("--workspace", default="Home Base")
    apply.add_argument("--no-kid", action="store_true")
    sub.add_parser("reset")
    ns = parser.parse_args(argv)

    wizard = FirstRunWizard()
    if ns.cmd == "status":
        out = wizard.status()
    elif ns.cmd == "apply":
        out = wizard.apply(
            hostname=ns.hostname,
            profile_id=ns.profile_id,
            display_name=ns.display_name,
            mode_default=ns.mode,
            workspace_name=ns.workspace,
            enable_kid=not ns.no_kid,
        )
    elif ns.cmd == "reset":
        out = wizard.reset()
    else:
        return 2
    print(json.dumps(out, indent=2, sort_keys=True, default=str))
    return 0 if out.get("ok") else 1


if __name__ == "__main__":
    raise SystemExit(main())

