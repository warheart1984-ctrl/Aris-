#!/usr/bin/env python3
"""CoGOS Nova REPL entrypoint (Phase 0)."""

from __future__ import annotations

import os
import sys
from pathlib import Path

ROOT = Path(os.environ.get("COGOS_ROOT", Path(__file__).resolve().parents[1]))
RUNTIME = ROOT / "runtime"
os.environ.setdefault("COGOS_ROOT", str(ROOT))

for p in (RUNTIME, RUNTIME / "ul", RUNTIME / "voss"):
    s = str(p)
    if s not in sys.path:
        sys.path.insert(0, s)

from cogos_runtime import main  # noqa: E402

if __name__ == "__main__":
    main()
