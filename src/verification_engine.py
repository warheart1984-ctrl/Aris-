from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any

from .constants_runtime import SPEECH_CHAIN, SPEECH_CODE, SPEECH_STATE, SPEECH_VERIFICATION
from .law_context_builder import RuntimeLawContext
from .law_ledger import LawLedger


@dataclass(frozen=True, slots=True)
class VerificationReport:
    passed: bool
    speech_state: str
    reason: str
    checks: dict[str, bool]
    recorded_at: str
    false_verification: bool
    speech_chain: tuple[str, ...]

    def payload(self) -> dict[str, Any]:
        return {
            "passed": self.passed,
            "speech_state": self.speech_state,
            "reason": self.reason,
            "checks": self.checks,
            "recorded_at": self.recorded_at,
            "false_verification": self.false_verification,
            "speech_chain": list(self.speech_chain),
        }


class VerificationEngine:
    def __init__(self, ledger: LawLedger) -> None:
        self.ledger = ledger

    def verify(
        self,
        *,
        context: RuntimeLawContext,
        result: dict[str, Any],
        repo_changed: bool,
        payload_ok: bool,
    ) -> VerificationReport:
        false_verification = any(
            bool(result.get(key))
            for key in ("1001_pass", "verification_present", "verified", "law_verified")
        )
        has_artifacts = bool(result.get("verification_artifacts"))
        checks = {
            "state_present": context.state_present,
            "code_present": context.code_present or bool(result),
            "payload_ok": payload_ok,
            "verification_artifacts": has_artifacts or not repo_changed,
            "no_false_verification": not false_verification,
        }
        if all(checks.values()):
            speech_state = SPEECH_VERIFICATION
            passed = True
            reason = "Verification engine completed the full 0001 -> 1000 -> 1001 speech chain."
        elif checks["state_present"] and checks["code_present"]:
            speech_state = SPEECH_CODE
            passed = False
            reason = "Execution reached 1000 but did not satisfy 1001 verification."
        else:
            speech_state = SPEECH_STATE
            passed = False
            reason = "Execution did not satisfy the law of speech."
        report = VerificationReport(
            passed=passed,
            speech_state=speech_state,
            reason=reason,
            checks=checks,
            recorded_at=datetime.now(UTC).isoformat(),
            false_verification=false_verification,
            speech_chain=SPEECH_CHAIN,
        )
        self.ledger.record(
            "post_verification",
            {
                "context": context.payload(),
                "report": report.payload(),
            },
            require_success=True,
        )
        return report
