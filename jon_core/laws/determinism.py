"""Λ.1 Determinism Enforcer - Input fingerprinting + output hash comparison."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Callable
import hashlib
import json


@dataclass(frozen=True, slots=True)
class DeterminismResult:
    """Result of determinism check."""
    deterministic: bool
    input_fingerprint: str
    output_hash: str
    expected_hash: str | None
    message: str


class DeterminismEnforcer:
    """Enforces deterministic execution via input/output hashing."""

    def __init__(self, algorithm: str = "sha256"):
        self.algorithm = algorithm

    def fingerprint(self, *inputs: Any) -> str:
        """Generate deterministic fingerprint of inputs."""
        hasher = hashlib.new(self.algorithm)
        for inp in inputs:
            if isinstance(inp, (dict, list)):
                serialized = json.dumps(inp, sort_keys=True, separators=(",", ":"))
            else:
                serialized = str(inp)
            hasher.update(serialized.encode("utf-8"))
        return hasher.hexdigest()

    def hash_output(self, output: Any) -> str:
        """Generate hash of output."""
        hasher = hashlib.new(self.algorithm)
        if isinstance(output, (dict, list)):
            serialized = json.dumps(output, sort_keys=True, separators=(",", ":"))
        else:
            serialized = str(output)
        hasher.update(serialized.encode("utf-8"))
        return hasher.hexdigest()

    def check(self, func: Callable, *inputs: Any, expected_hash: str | None = None) -> DeterminismResult:
        """Execute function and verify determinism."""
        input_fp = self.fingerprint(*inputs)
        output = func(*inputs)
        output_hash = self.hash_output(output)

        if expected_hash is not None:
            deterministic = output_hash == expected_hash
            msg = "Matches expected" if deterministic else "Output hash mismatch"
        else:
            # Run twice to verify internal determinism
            output2 = func(*inputs)
            output_hash2 = self.hash_output(output2)
            deterministic = output_hash == output_hash2
            msg = "Self-consistent" if deterministic else "Non-deterministic: repeated runs differ"

        return DeterminismResult(
            deterministic=deterministic,
            input_fingerprint=input_fp,
            output_hash=output_hash,
            expected_hash=expected_hash,
            message=msg,
        )

    def assert_deterministic(self, func: Callable, *inputs: Any, expected_hash: str | None = None) -> Any:
        """Execute and raise if non-deterministic."""
        result = self.check(func, *inputs, expected_hash=expected_hash)
        if not result.deterministic:
            raise ValueError(f"Determinism violation: {result.message}")
        return func(*inputs)