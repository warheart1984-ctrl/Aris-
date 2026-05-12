#!/usr/bin/env bash
set -euo pipefail

usage() {
  cat <<'USAGE'
Usage:
  bash scripts/build_trixie_cogos.sh /path/to/TrixiePup64-Wayland-2601-260502.iso

Output:
  output/project-infi-aris-trixie-full-os-v10.iso

Required Linux tools:
  unsquashfs mksquashfs xorriso rsync
USAGE
}

if [[ "${1:-}" == "-h" || "${1:-}" == "--help" || $# -ne 1 ]]; then
  usage
  exit 0
fi

ISO="$(readlink -f "$1")"
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
WORK="${COGOS_WORK:-$ROOT/work}"
OUT="${COGOS_OUT:-$ROOT/output/project-infi-aris-trixie-full-os-v10.iso}"
PAYLOAD="$ROOT/payload"

for tool in unsquashfs mksquashfs xorriso rsync find; do
  command -v "$tool" >/dev/null 2>&1 || {
    echo "Missing required tool: $tool" >&2
    exit 2
  }
done

if [[ ! -f "$ISO" ]]; then
  echo "ISO not found: $ISO" >&2
  exit 3
fi

rm -rf "$WORK"
mkdir -p "$WORK/iso" "$WORK/rootfs" "$ROOT/output"

echo "[1/8] Extract ISO contents"
xorriso -osirrox on -indev "$ISO" -extract / "$WORK/iso" >/dev/null

echo "[3/8] Locate SquashFS"
SFS_SOURCE="$(find "$WORK/iso" -maxdepth 3 -type f -name 'puppy_*.sfs' | head -n 1)"
if [[ -z "$SFS_SOURCE" ]]; then
  SFS_SOURCE="$(find "$WORK/iso" -maxdepth 3 -type f \( -name '*.sfs' -o -name '*.squashfs' \) | sort | head -n 1)"
fi
if [[ -z "$SFS_SOURCE" ]]; then
  echo "No SquashFS root file found inside ISO." >&2
  exit 4
fi
SFS_NAME="$(basename "$SFS_SOURCE")"

echo "[4/8] Extract root filesystem: $SFS_NAME"
unsquashfs -f -d "$WORK/rootfs" "$SFS_SOURCE"

echo "[5/8] Stage Project Infi / ARIS payload"
rsync -aH "$PAYLOAD/" "$WORK/rootfs/"
chmod +x "$WORK/rootfs/opt/cogos/bin/cognitive_init" "$WORK/rootfs/opt/cogos/bin/cogos_shell" "$WORK/rootfs/opt/cogos/bin/cogos_boot.py" "$WORK/rootfs/opt/cogos/bin/cogos_daemon.py" "$WORK/rootfs/opt/cogos/bin/cogos_dashboard.py" "$WORK/rootfs/opt/cogos/bin/cogos_operator_boot.py"

echo "[6/8] Preserve native init and install CoGOS startup layer"
chmod +x "$WORK/rootfs/etc/init.d/90cogos" "$WORK/rootfs/usr/local/bin/cogos-status" "$WORK/rootfs/usr/local/bin/cogos-shell" "$WORK/rootfs/usr/local/bin/cogos-doctor" "$WORK/rootfs/usr/local/bin/cogos-daemon" "$WORK/rootfs/usr/local/bin/cogos-run" "$WORK/rootfs/usr/local/bin/cogos-task" "$WORK/rootfs/usr/local/bin/cogos-trace" "$WORK/rootfs/usr/local/bin/cogos-law" "$WORK/rootfs/usr/local/bin/cogos-admit" "$WORK/rootfs/usr/local/bin/cogos-snapshot" "$WORK/rootfs/usr/local/bin/cogos-reflect" "$WORK/rootfs/usr/local/bin/cogos-dashboard" "$WORK/rootfs/usr/local/bin/cogos-dashboard-start" "$WORK/rootfs/usr/local/bin/cogos-dashboard-stop" "$WORK/rootfs/usr/local/bin/cogos-desktop-hint" "$WORK/rootfs/usr/local/bin/cogos-verify-trace" "$WORK/rootfs/usr/local/bin/cogos-governance-test" "$WORK/rootfs/usr/local/bin/cogos-module" "$WORK/rootfs/usr/local/bin/cogos-traits" "$WORK/rootfs/usr/local/bin/cogos-patterns" "$WORK/rootfs/usr/local/bin/cogos-proof" "$WORK/rootfs/usr/local/bin/cogos-operator" "$WORK/rootfs/usr/local/bin/cogos-perf"
chmod +x "$WORK/rootfs/opt/cogos/modules/local/trace_analyzer/trace_analyzer.py" "$WORK/rootfs/opt/cogos/modules/local/bad_mutator/bad_mutator.py" "$WORK/rootfs/opt/cogos/modules/local/invalid_output/invalid_output.py" "$WORK/rootfs/opt/cogos/modules/local/slow_module/slow_module.py"
if [[ -L "$WORK/rootfs/usr/sbin/init" && "$(readlink "$WORK/rootfs/usr/sbin/init")" == "/opt/cogos/bin/cognitive_init" ]]; then
  if [[ -e "$WORK/rootfs/usr/sbin/init.original" ]]; then
    rm "$WORK/rootfs/usr/sbin/init"
    mv "$WORK/rootfs/usr/sbin/init.original" "$WORK/rootfs/usr/sbin/init"
  else
    echo "Native init was replaced but no init.original exists." >&2
    exit 5
  fi
fi

echo "[7/8] Rebuild SquashFS"
mksquashfs "$WORK/rootfs" "$SFS_SOURCE" -comp xz -b 1M -noappend -all-root

echo "[8/8] Rebuild ISO"
if [[ -f "$WORK/iso/isolinux.bin" ]]; then
  EFI_ARGS=()
  if [[ -f "$WORK/iso/boot/efi.img" ]]; then
    EFI_ARGS=(-eltorito-alt-boot -e boot/efi.img -no-emul-boot)
  fi

  xorriso -as mkisofs -D -r -J -l \
    -V "ISOIMAGE" \
    -o "$OUT" \
    -b isolinux.bin \
    -c boot/boot.catalog \
    -no-emul-boot \
    -boot-load-size 4 \
    -boot-info-table \
    "${EFI_ARGS[@]}" \
    -isohybrid-gpt-basdat \
    "$WORK/iso"
else
  xorriso -as mkisofs -D -r -J -l -V "ISOIMAGE" -o "$OUT" "$WORK/iso"
fi

echo "Built: $OUT"
