"""Detached manifest signatures for CoGOS package/update metadata."""

from __future__ import annotations

import hashlib
import hmac
import json
import time
from pathlib import Path
from typing import Any, Dict, Optional

from governance_invariant_engine import cogos_root


SIGNATURE_VERSION = "cogos-signature-v1"


def canonical_json(data: Any) -> bytes:
    return json.dumps(data, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode("utf-8")


def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as fh:
        for chunk in iter(lambda: fh.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def trust_config_path() -> Path:
    return cogos_root() / "config" / "trust_keys.json"


def load_trust_config() -> Dict[str, Any]:
    path = trust_config_path()
    if not path.exists():
        return {"version": "1.0", "active_key": "", "keys": []}
    return json.loads(path.read_text(encoding="utf-8-sig"))


def _key_by_id(key_id: str) -> Optional[Dict[str, Any]]:
    for key in load_trust_config().get("keys", []):
        if key.get("id") == key_id and key.get("enabled", True):
            return key
    return None


def active_key() -> Dict[str, Any]:
    cfg = load_trust_config()
    key_id = cfg.get("active_key")
    key = _key_by_id(str(key_id))
    if not key:
        raise ValueError(f"active signing key not found or disabled: {key_id}")
    return key


def _manifest_without_signature(data: Dict[str, Any]) -> Dict[str, Any]:
    return {k: v for k, v in data.items() if k not in {"signature", "signatures"}}


def sign_manifest_file(path: Path, *, key_id: Optional[str] = None, signature_path: Optional[Path] = None) -> Dict[str, Any]:
    key = _key_by_id(key_id) if key_id else active_key()
    if not key:
        raise ValueError(f"signing key not found: {key_id}")
    data = json.loads(path.read_text(encoding="utf-8-sig"))
    payload = canonical_json(_manifest_without_signature(data))
    sig = hmac.new(str(key["secret"]).encode("utf-8"), payload, hashlib.sha256).hexdigest()
    out = {
        "version": SIGNATURE_VERSION,
        "key_id": key["id"],
        "algorithm": "HMAC-SHA256",
        "manifest": str(path.name),
        "manifest_sha256": hashlib.sha256(payload).hexdigest(),
        "file_sha256": sha256_file(path),
        "signed_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "signature": sig,
    }
    sig_path = signature_path or path.with_suffix(path.suffix + ".sig")
    sig_path.write_text(json.dumps(out, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return out


def verify_manifest_file(path: Path, signature_path: Optional[Path] = None) -> Dict[str, Any]:
    sig_path = signature_path or path.with_suffix(path.suffix + ".sig")
    if not path.exists():
        return {"ok": False, "error": f"manifest missing: {path}"}
    if not sig_path.exists():
        return {"ok": False, "error": f"signature missing: {sig_path}", "manifest": str(path)}
    try:
        data = json.loads(path.read_text(encoding="utf-8-sig"))
        sig = json.loads(sig_path.read_text(encoding="utf-8-sig"))
        if sig.get("version") != SIGNATURE_VERSION:
            return {"ok": False, "error": "unsupported signature version", "signature": str(sig_path)}
        key = _key_by_id(str(sig.get("key_id")))
        if not key:
            return {"ok": False, "error": f"trusted key not found: {sig.get('key_id')}", "signature": str(sig_path)}
        payload = canonical_json(_manifest_without_signature(data))
        expected = hmac.new(str(key["secret"]).encode("utf-8"), payload, hashlib.sha256).hexdigest()
        manifest_hash = hashlib.sha256(payload).hexdigest()
        ok = hmac.compare_digest(expected, str(sig.get("signature", ""))) and manifest_hash == sig.get("manifest_sha256")
        return {
            "ok": ok,
            "manifest": str(path),
            "signature": str(sig_path),
            "key_id": sig.get("key_id"),
            "algorithm": sig.get("algorithm"),
            "manifest_sha256": manifest_hash,
            "error": "" if ok else "signature mismatch",
        }
    except Exception as exc:
        return {"ok": False, "error": str(exc), "manifest": str(path), "signature": str(sig_path)}


def verify_core_manifests(root: Optional[Path] = None) -> Dict[str, Any]:
    root = root or cogos_root()
    checks = [
        verify_manifest_file(root / "config" / "release_manifest.json"),
        verify_manifest_file(root / "config" / "package_catalog.json"),
        verify_manifest_file(root / "config" / "update_channel.json"),
    ]
    return {"ok": all(c.get("ok") for c in checks), "checks": checks}

