#!/usr/bin/env bash
set -euo pipefail

REPO_ROOT="${REPO_ROOT:-$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)}"
ISO="${1:-$REPO_ROOT/AI OS Debian Build/output/project-infi-cogos-12.3.0-control-center.iso}"
OUT="${COGOS_QEMU_OUT:-$REPO_ROOT/AI OS Debian Build/output/proofs/qemu}"
PROOF_SHARE="${COGOS_QEMU_PROOF_SHARE:-/tmp/cogos-proofs}"
WAIT_SECONDS="${COGOS_QEMU_WAIT:-90}"
BOOT_KEY_DELAY="${COGOS_QEMU_BOOT_KEY_DELAY:-5}"
QMP_HOST="${COGOS_QMP_HOST:-127.0.0.1}"
QMP_PORT="${COGOS_QMP_PORT:-45454}"
SERIAL_MODE="${COGOS_QEMU_SERIAL:-file}"

mkdir -p "$OUT" "$PROOF_SHARE"
SCREEN_TMP="/tmp/cogos-screen.ppm"
rm -f "$SCREEN_TMP" "$OUT/screen.ppm" "$OUT/qmp.log"

SERIAL_ARGS=(-serial "file:$OUT/serial-qmp.log" -display none)
if [[ "$SERIAL_MODE" == "stdio" ]]; then
  SERIAL_ARGS=(-nographic -serial mon:stdio -vga std)
fi

qemu-system-x86_64 \
  -m "${COGOS_QEMU_MEMORY:-4096}" \
  -smp "${COGOS_QEMU_CPUS:-4}" \
  -cdrom "$ISO" \
  -boot d \
  "${SERIAL_ARGS[@]}" \
  -qmp "tcp:$QMP_HOST:$QMP_PORT,server,nowait" \
  -fsdev "local,id=proofs,path=$PROOF_SHARE,security_model=mapped" \
  -device "virtio-9p-pci,fsdev=proofs,mount_tag=proofs" \
  -no-reboot \
  > "$OUT/qemu-stdout.log" \
  2> "$OUT/qemu-stderr.log" &
QPID=$!
echo "$QPID" > "$OUT/qemu-pid.txt"

sleep "$BOOT_KEY_DELAY"

PYTHON="${PYTHON:-}"
if [[ -z "$PYTHON" ]]; then
  if command -v python3 >/dev/null 2>&1; then
    PYTHON="$(command -v python3)"
  elif command -v python >/dev/null 2>&1; then
    PYTHON="$(command -v python)"
  elif [[ -x "/mnt/e/project-infi/AAIS-main/.runtime/python312-store-copy/python.exe" ]]; then
    PYTHON="/mnt/e/project-infi/AAIS-main/.runtime/python312-store-copy/python.exe"
  else
    echo "No Python found for QMP control." >&2
    kill "$QPID" 2>/dev/null || true
    wait "$QPID" || true
    exit 127
  fi
fi

"$PYTHON" - "$QMP_HOST" "$QMP_PORT" "$SCREEN_TMP" "$OUT/qmp.log" <<'PY'
import json
import socket
import sys

qmp_host, qmp_port, screen_path, log_path = sys.argv[1:5]
sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
sock.connect((qmp_host, int(qmp_port)))
log = []

def recv():
    data = sock.recv(65536).decode("utf-8", "replace")
    log.append(data)
    return data

def send(payload):
    sock.sendall(json.dumps(payload).encode("utf-8") + b"\r\n")
    return recv()

recv()
send({"execute": "qmp_capabilities"})
send({
    "execute": "input-send-event",
    "arguments": {
        "events": [
            {"type": "key", "data": {"down": True, "key": {"type": "qcode", "data": "ret"}}},
            {"type": "key", "data": {"down": False, "key": {"type": "qcode", "data": "ret"}}},
        ]
    },
})
PY

sleep "$WAIT_SECONDS"

"$PYTHON" - "$QMP_HOST" "$QMP_PORT" "$SCREEN_TMP" "$OUT/qmp.log" <<'PY'
import json
import socket
import sys

qmp_host, qmp_port, screen_path, log_path = sys.argv[1:5]
sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
sock.connect((qmp_host, int(qmp_port)))
log = []

def recv():
    data = sock.recv(65536).decode("utf-8", "replace")
    log.append(data)
    return data

def send(payload):
    sock.sendall(json.dumps(payload).encode("utf-8") + b"\r\n")
    return recv()

recv()
send({"execute": "qmp_capabilities"})
send(
    {
        "execute": "human-monitor-command",
        "arguments": {"command-line": f"screendump {screen_path}"},
    }
)
send({"execute": "quit"})
with open(log_path, "w", encoding="utf-8") as fh:
    fh.write("\n".join(log))
PY

wait "$QPID" || true
if [[ -f "$SCREEN_TMP" ]]; then
  cp "$SCREEN_TMP" "$OUT/screen.ppm"
fi
ls -l "$OUT"
