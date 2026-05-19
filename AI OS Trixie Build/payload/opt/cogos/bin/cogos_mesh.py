#!/usr/bin/env python3
"""CoGOS mesh / reasoning exchange CLI (Phase 2)."""

from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path

ROOT = Path(os.environ.get("COGOS_ROOT", "/opt/cogos"))
sys.path.insert(0, str(ROOT / "runtime"))

from mesh_identity import MeshIdentityStore  # noqa: E402
from reasoning_exchange import ReasoningExchangeNode  # noqa: E402


def main() -> int:
    parser = argparse.ArgumentParser(description="CoGOS mesh reasoning exchange")
    sub = parser.add_subparsers(dest="cmd")

    sub.add_parser("identity", help="Show device sigil bundle")
    sub.add_parser("status", help="Inbox/outbox summary")

    prop = sub.add_parser("propose", help="Propose reasoning message")
    prop.add_argument("--kind", default="reasoning_proposal")
    prop.add_argument("--payload", default="{}")

    recv = sub.add_parser("receive", help="Evaluate inbound message JSON file")
    recv.add_argument("file")

    trust = sub.add_parser("trust", help="Trust a peer device")
    trust.add_argument("device_id")
    trust.add_argument("--sigil", default="")

    args = parser.parse_args()
    node = ReasoningExchangeNode()

    if args.cmd == "identity":
        print(json.dumps(MeshIdentityStore().export_exchange_bundle(), indent=2))
        return 0
    if args.cmd == "status":
        print(json.dumps(node.list_recent(), indent=2))
        return 0
    if args.cmd == "propose":
        payload = json.loads(args.payload)
        msg = node.propose(payload, kind=args.kind)
        print(json.dumps(msg.to_dict(), indent=2))
        return 0
    if args.cmd == "receive":
        raw = json.loads(Path(args.file).read_text(encoding="utf-8-sig"))
        result = node.receive(raw)
        print(json.dumps(result.message.to_dict(), indent=2))
        return 0 if result.admitted else 1
    if args.cmd == "trust":
        print(json.dumps(node.trust_peer(args.device_id, args.sigil or None), indent=2))
        return 0
    parser.print_help()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
