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

if [[ "${1:-}" == "-h" || "${1:-}" == "--help" ]]; then
  usage
  exit 0
fi
if [[ $# -ne 1 ]]; then
  usage >&2
  exit 1
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

echo "[1/6] Extract ISO contents"
xorriso -osirrox on -indev "$ISO" -extract / "$WORK/iso" >/dev/null

echo "[2/6] Locate SquashFS"
SFS_SOURCE="$(find "$WORK/iso" -maxdepth 3 -type f -name 'puppy_*.sfs' | head -n 1)"
if [[ -z "$SFS_SOURCE" ]]; then
  SFS_SOURCE="$(find "$WORK/iso" -maxdepth 3 -type f \( -name '*.sfs' -o -name '*.squashfs' \) | sort | head -n 1)"
fi
if [[ -z "$SFS_SOURCE" ]]; then
  echo "No SquashFS root file found inside ISO." >&2
  exit 4
fi
SFS_NAME="$(basename "$SFS_SOURCE")"

echo "[3/6] Extract root filesystem: $SFS_NAME"
unsquashfs -f -d "$WORK/rootfs" "$SFS_SOURCE"

echo "[4/6] Stage Project Infi / ARIS payload"
rsync -aH "$PAYLOAD/" "$WORK/rootfs/"
chmod +x "$WORK/rootfs/opt/cogos/bin/"* "$WORK/rootfs/etc/init.d/90cogos" "$WORK/rootfs/usr/local/bin/"cogos-* "$WORK/rootfs/opt/cogos/modules/local/"*/*.py

# Preserve native init: undo any earlier build that replaced it with cognitive_init.
if [[ -L "$WORK/rootfs/usr/sbin/init" && "$(readlink "$WORK/rootfs/usr/sbin/init")" == "/opt/cogos/bin/cognitive_init" ]]; then
  if [[ -e "$WORK/rootfs/usr/sbin/init.original" ]]; then
    rm "$WORK/rootfs/usr/sbin/init"
    mv "$WORK/rootfs/usr/sbin/init.original" "$WORK/rootfs/usr/sbin/init"
  else
    echo "Native init was replaced but no init.original exists." >&2
    exit 5
  fi
fi

echo "[5/6] Rebuild SquashFS"
mksquashfs "$WORK/rootfs" "$SFS_SOURCE" -comp xz -b 1M -noappend -all-root

echo "[6/6] Rebuild ISO"
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
