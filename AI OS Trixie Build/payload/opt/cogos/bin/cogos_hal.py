#!/usr/bin/env python3
"""HAL observation daemon (Phase 1)."""

from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path

ROOT = Path(os.environ.get("COGOS_ROOT", "/opt/cogos"))
RUNTIME = ROOT / "runtime"
for p in (RUNTIME,):
    s = str(p)
    if s not in sys.path:
        sys.path.insert(0, s)

from hal_service import observe_hal, run_daemon, write_hal_snapshot  # noqa: E402


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--once", action="store_true")
    parser.add_argument("--daemon", action="store_true")
    parser.add_argument("--interval", type=float, default=30.0)
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args()

    if args.daemon:
        pid_path = Path("/run/cogos-hal.pid")
        pid_path.write_text(str(os.getpid()) + "\n", encoding="utf-8")
        run_daemon(interval=args.interval)
        return 0

    data = observe_hal()
    path = write_hal_snapshot(data)
    if args.json:
        import json

        print(json.dumps(data, indent=2))
    else:
        print(f"HAL snapshot written: {path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
