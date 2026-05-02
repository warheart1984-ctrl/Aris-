from __future__ import annotations

try:
    from .desktop import main as _desktop_main
except ImportError:
    from evolving_ai.aris_demo.desktop import main as _desktop_main


def main(argv: list[str] | None = None) -> int:
    return _desktop_main(argv, default_profile="v2")


if __name__ == "__main__":
    raise SystemExit(main())