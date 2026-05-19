#!/usr/bin/env bash
set -euo pipefail

# Smoke-boot the CoGOS ISO under QEMU when qemu-system-x86_64 is installed.
# This does not modify disks; it boots the ISO as a live image with serial
# output attached to the terminal.

REPO_ROOT="${REPO_ROOT:-$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)}"
ISO="${1:-$REPO_ROOT/AI OS Debian Build/output/project-infi-cogos-12.1.0-phase3.iso}"
MEMORY="${COGOS_QEMU_MEMORY:-4096}"
CPUS="${COGOS_QEMU_CPUS:-2}"

if ! command -v qemu-system-x86_64 >/dev/null 2>&1; then
  cat >&2 <<'EOF'
qemu-system-x86_64 is not installed.

Install on Debian/Ubuntu/WSL:
  sudo apt-get update
  sudo apt-get install -y qemu-system-x86 ovmf

Then rerun:
  bash scripts/linux-qemu-boot-test-cogos.sh
EOF
  exit 127
fi

if [[ ! -f "$ISO" ]]; then
  echo "ISO not found: $ISO" >&2
  exit 2
fi

exec qemu-system-x86_64 \
  -m "$MEMORY" \
  -smp "$CPUS" \
  -cdrom "$ISO" \
  -boot d \
  -serial mon:stdio \
  -display none \
  -no-reboot
