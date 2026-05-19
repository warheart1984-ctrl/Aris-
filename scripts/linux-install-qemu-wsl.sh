#!/usr/bin/env bash
set -euo pipefail

apt-get clean
rm -rf /var/lib/apt/lists/*
cat > /etc/apt/apt.conf.d/99no-translations-codex <<'EOF'
Acquire::Languages "none";
EOF
apt-get update
apt-get install -y qemu-system-x86 ovmf
