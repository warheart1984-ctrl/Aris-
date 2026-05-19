#!/usr/bin/env bash
set -euo pipefail

# Linux/WSL helper for building the CoGOS Debian ISO.
# Run from the repo root, or pass REPO_ROOT=/path/to/project-infi.

REPO_ROOT="${REPO_ROOT:-$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)}"
BASE_ISO="${1:-$REPO_ROOT/debian-live-13.4.0-amd64-cinnamon.iso}"
BUILD_DIR="$REPO_ROOT/AI OS Debian Build"
STAMP="$(date -u +%Y%m%d%H%M%S)"

export COGOS_WORK="${COGOS_WORK:-/tmp/project-infi-cogos-iso-$STAMP}"
export COGOS_OUT="${COGOS_OUT:-$BUILD_DIR/output/project-infi-cogos-12.1.0-phase3.iso}"

cd "$BUILD_DIR"
exec bash scripts/build_debian_cogos.sh "$BASE_ISO"
