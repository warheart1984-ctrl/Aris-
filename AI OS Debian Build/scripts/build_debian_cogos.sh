#!/usr/bin/env bash
set -euo pipefail

usage() {
  cat <<'USAGE'
Usage:
  bash scripts/build_debian_cogos.sh [/path/to/debian-live-13.4.0-amd64-cinnamon.iso]

Default ISO path (repo top level):
  ../debian-live-13.4.0-amd64-cinnamon.iso

Output:
  output/project-infi-aris-debian-cinnamon-full-os-v12.iso

Reuses CoGOS payload from:
  ../AI OS Trixie Build/payload

Required Linux tools:
  unsquashfs mksquashfs xorriso rsync find

Notes:
  Set COGOS_XATTRS=1 to preserve SquashFS xattrs. The default is an
  unprivileged WSL-friendly path that uses -no-xattrs because Debian live
  images contain security.capability entries that require root to restore.
USAGE
}

if [[ "${1:-}" == "-h" || "${1:-}" == "--help" ]]; then
  usage
  exit 0
fi

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
REPO_ROOT="$(cd "$ROOT/.." && pwd)"
ISO="${1:-$REPO_ROOT/debian-live-13.4.0-amd64-cinnamon.iso}"
WORK="${COGOS_WORK:-$ROOT/work}"
OUT="${COGOS_OUT:-$ROOT/output/project-infi-aris-debian-cinnamon-full-os-v12.iso}"
PAYLOAD="${COGOS_PAYLOAD:-$REPO_ROOT/AI OS Trixie Build/payload}"

for tool in unsquashfs mksquashfs xorriso rsync find grep; do
  command -v "$tool" >/dev/null 2>&1 || {
    echo "Missing required tool: $tool" >&2
    exit 2
  }
done

if [[ ! -f "$ISO" ]]; then
  echo "ISO not found: $ISO" >&2
  exit 3
fi

if [[ ! -d "$PAYLOAD" ]]; then
  echo "CoGOS payload not found: $PAYLOAD" >&2
  exit 3
fi

ISO="$(readlink -f "$ISO")"
rm -rf "$WORK"
mkdir -p "$WORK/iso" "$WORK/rootfs" "$ROOT/output"

echo "[1/8] Extract ISO contents"
xorriso -osirrox on -indev "$ISO" -extract / "$WORK/iso" >/dev/null
chmod -R u+w "$WORK/iso"

echo "[2/8] Locate Debian live SquashFS root"
SFS_SOURCE=""
for candidate in \
  "$WORK/iso/live/filesystem.squashfs" \
  "$(find "$WORK/iso/live" -maxdepth 1 -type f -name 'filesystem*.squashfs' 2>/dev/null | head -n 1)" \
  "$(find "$WORK/iso" -maxdepth 3 -type f -name '*.squashfs' 2>/dev/null | sort | head -n 1)"; do
  if [[ -n "$candidate" && -f "$candidate" ]]; then
    SFS_SOURCE="$candidate"
    break
  fi
done
if [[ -z "$SFS_SOURCE" ]]; then
  echo "No SquashFS root file found inside ISO." >&2
  exit 4
fi
SFS_NAME="$(basename "$SFS_SOURCE")"
echo "Using root filesystem image: $SFS_SOURCE"

echo "[3/8] Extract root filesystem: $SFS_NAME"
if [[ "${COGOS_XATTRS:-0}" == "1" ]]; then
  unsquashfs -f -d "$WORK/rootfs" "$SFS_SOURCE"
else
  unsquashfs -no-xattrs -f -d "$WORK/rootfs" "$SFS_SOURCE"
fi

echo "[4/8] Stage Project Infi / ARIS CoGOS payload (Trixie schema)"
rsync -aH "$PAYLOAD/" "$WORK/rootfs/"
chmod +x \
  "$WORK/rootfs/opt/cogos/bin/cognitive_init" \
  "$WORK/rootfs/opt/cogos/bin/cogos_shell" \
  "$WORK/rootfs/opt/cogos/bin/cogos_boot.py" \
  "$WORK/rootfs/opt/cogos/bin/cogos_daemon.py" \
  "$WORK/rootfs/opt/cogos/bin/cogos_dashboard.py" \
  "$WORK/rootfs/opt/cogos/bin/cogos_operator_boot.py" \
  "$WORK/rootfs/opt/cogos/bin/cogos_nova_repl.py" \
  "$WORK/rootfs/opt/cogos/bin/cogos_update.py" \
  "$WORK/rootfs/opt/cogos/bin/cogos_hal.py" \
  "$WORK/rootfs/opt/cogos/bin/cogos_desktop.py" \
  "$WORK/rootfs/opt/cogos/bin/cogos_mesh.py" \
  "$WORK/rootfs/opt/cogos/bin/cogos_creative.py" \
  "$WORK/rootfs/opt/cogos/bin/cogos_pkg.py" \
  "$WORK/rootfs/opt/cogos/bin/cogos_backup.py" \
  "$WORK/rootfs/opt/cogos/bin/cogos_eval.py" \
  "$WORK/rootfs/opt/cogos/bin/cogos_cockpit.py" \
  "$WORK/rootfs/opt/cogos/bin/cogos_ship.py" \
  "$WORK/rootfs/opt/cogos/bin/cogos_auto.py" \
  "$WORK/rootfs/opt/cogos/bin/cogos_ul_stdlib.py" \
  "$WORK/rootfs/opt/cogos/bin/cogos_device_storage.py" \
  "$WORK/rootfs/opt/cogos/bin/cogos_first_run.py" \
  "$WORK/rootfs/opt/cogos/bin/cogos_manifest.py" \
  "$WORK/rootfs/opt/cogos/bin/cogos_recovery.py"

echo "[5/8] Install CoGOS operator layer"
chmod +x "$WORK/rootfs/etc/init.d/90cogos" \
  "$WORK/rootfs/usr/local/bin/cogos-status" \
  "$WORK/rootfs/usr/local/bin/cogos-shell" \
  "$WORK/rootfs/usr/local/bin/cogos-doctor" \
  "$WORK/rootfs/usr/local/bin/cogos-daemon" \
  "$WORK/rootfs/usr/local/bin/cogos-run" \
  "$WORK/rootfs/usr/local/bin/cogos-task" \
  "$WORK/rootfs/usr/local/bin/cogos-trace" \
  "$WORK/rootfs/usr/local/bin/cogos-law" \
  "$WORK/rootfs/usr/local/bin/cogos-admit" \
  "$WORK/rootfs/usr/local/bin/cogos-snapshot" \
  "$WORK/rootfs/usr/local/bin/cogos-reflect" \
  "$WORK/rootfs/usr/local/bin/cogos-dashboard" \
  "$WORK/rootfs/usr/local/bin/cogos-dashboard-start" \
  "$WORK/rootfs/usr/local/bin/cogos-dashboard-stop" \
  "$WORK/rootfs/usr/local/bin/cogos-desktop-hint" \
  "$WORK/rootfs/usr/local/bin/cogos-verify-trace" \
  "$WORK/rootfs/usr/local/bin/cogos-governance-test" \
  "$WORK/rootfs/usr/local/bin/cogos-module" \
  "$WORK/rootfs/usr/local/bin/cogos-traits" \
  "$WORK/rootfs/usr/local/bin/cogos-patterns" \
  "$WORK/rootfs/usr/local/bin/cogos-proof" \
  "$WORK/rootfs/usr/local/bin/cogos-operator" \
  "$WORK/rootfs/usr/local/bin/cogos-perf" \
  "$WORK/rootfs/usr/local/bin/cogos-pid1-proof" \
  "$WORK/rootfs/usr/local/bin/cogos-ul" \
  "$WORK/rootfs/usr/local/bin/cogos-voss" \
  "$WORK/rootfs/usr/local/bin/cogos-desktop-start" \
  "$WORK/rootfs/usr/local/bin/cogos-hal-start" \
  "$WORK/rootfs/usr/local/bin/cogos-cockpit" \
  "$WORK/rootfs/usr/local/bin/cogos-pkg" \
  "$WORK/rootfs/usr/local/bin/cogos-backup" \
  "$WORK/rootfs/usr/local/bin/cogos-eval" \
  "$WORK/rootfs/usr/local/bin/cogos-ship" \
  "$WORK/rootfs/usr/local/bin/cogos-guest-proof" \
  "$WORK/rootfs/usr/local/bin/cogos-persist" \
  "$WORK/rootfs/usr/local/bin/cogos-install" \
  "$WORK/rootfs/usr/local/bin/cogos-auto" \
  "$WORK/rootfs/usr/local/bin/cogos-ul-stdlib" \
  "$WORK/rootfs/usr/local/bin/cogos-device-storage" \
  "$WORK/rootfs/usr/local/bin/cogos-first-run" \
  "$WORK/rootfs/usr/local/bin/cogos-manifest" \
  "$WORK/rootfs/usr/local/bin/cogos-recovery"
chmod +x \
  "$WORK/rootfs/opt/cogos/modules/local/trace_analyzer/trace_analyzer.py" \
  "$WORK/rootfs/opt/cogos/modules/local/bad_mutator/bad_mutator.py" \
  "$WORK/rootfs/opt/cogos/modules/local/invalid_output/invalid_output.py" \
  "$WORK/rootfs/opt/cogos/modules/local/slow_module/slow_module.py"

echo "[6/8] Install CoGOS PID 1 gatekeeper"
NATIVE_INIT_REAL=""
for candidate in \
  "$WORK/rootfs/usr/sbin/init" \
  "$WORK/rootfs/sbin/init"; do
  if [[ -L "$candidate" || -f "$candidate" ]]; then
    NATIVE_INIT_REAL="$(readlink -f "$candidate" 2>/dev/null || echo "$candidate")"
    break
  fi
done
if [[ -z "$NATIVE_INIT_REAL" || ! -e "$NATIVE_INIT_REAL" ]]; then
  echo "Native init not found at /usr/sbin/init or /sbin/init." >&2
  exit 5
fi
if [[ "$NATIVE_INIT_REAL" == "$WORK/rootfs/opt/cogos/bin/cognitive_init" ]]; then
  echo "Native init already points to CoGOS before preservation." >&2
  exit 5
fi
if [[ ! -e "$WORK/rootfs/usr/sbin/init.original" ]]; then
  cp -a "$NATIVE_INIT_REAL" "$WORK/rootfs/usr/sbin/init.original"
fi
chmod +x "$WORK/rootfs/usr/sbin/init.original"
rm -f "$WORK/rootfs/usr/sbin/init"
ln -s /opt/cogos/bin/cognitive_init "$WORK/rootfs/usr/sbin/init"
if [[ -e "$WORK/rootfs/sbin" ]]; then
  rm -f "$WORK/rootfs/sbin/init"
  ln -s /opt/cogos/bin/cognitive_init "$WORK/rootfs/sbin/init"
fi
[[ "$(readlink "$WORK/rootfs/usr/sbin/init")" == "/opt/cogos/bin/cognitive_init" ]] || {
  echo "/usr/sbin/init does not resolve to CoGOS cognitive_init." >&2
  exit 5
}
echo "Preserved native init: /usr/sbin/init.original from ${NATIVE_INIT_REAL#$WORK/rootfs}"

echo "[7/8] Rebuild SquashFS"
if [[ "${COGOS_XATTRS:-0}" == "1" ]]; then
  mksquashfs "$WORK/rootfs" "$SFS_SOURCE" -comp xz -b 1M -noappend -all-root
else
  mksquashfs "$WORK/rootfs" "$SFS_SOURCE" -comp xz -b 1M -noappend -all-root -no-xattrs
fi

echo "[8/8] Rebuild ISO (replay Debian live boot images from source ISO)"
rm -f "$OUT"
xorriso -indev "$ISO" -outdev "$OUT" \
  -boot_image any replay \
  -map "$WORK/iso" "/" \
  -commit >/dev/null

echo "Built: $OUT"
sha256sum "$OUT" | tee "${OUT}.sha256"
