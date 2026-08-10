"""Tests for Jon Core P0 Constitution components."""

import unittest
import time
from datetime import datetime, timezone

from jon_core.laws import (
    DeterminismEnforcer,
    DeterminismResult,
    AppendOnlyAuditEmitter,
    AuditRecord,
    CircuitBreaker,
    CircuitState,
    CircuitBreakerConfig,
    CircuitOpenError,
    IdentityBoundaryEnforcer,
    IdentityContext,
    IdentityLeakDetector,
    DriftMonitor,
    DriftScore,
    DriftDimension,
    InterruptHandler,
    InterruptRequest,
    InterruptReason,
    CorrectionInterface,
    KillSwitch,
    KillSwitchState,
    KillSwitchTrigger,
    SupremacyValidator,
    ValidationReport,
    ValidationResult,
    OverrideLockout,
)


class TestDeterminismEnforcer(unittest.TestCase):
    def test_fingerprint_consistency(self):
        enforcer = DeterminismEnforcer()
        fp1 = enforcer.fingerprint({"a": 1, "b": 2})
        fp2 = enforcer.fingerprint({"a": 1, "b": 2})
        self.assertEqual(fp1, fp2)

    def test_fingerprint_order_independent(self):
        enforcer = DeterminismEnforcer()
        fp1 = enforcer.fingerprint({"b": 2, "a": 1})
        fp2 = enforcer.fingerprint({"a": 1, "b": 2})
        self.assertEqual(fp1, fp2)

    def test_deterministic_function_passes(self):
        enforcer = DeterminismEnforcer()
        def pure_func(x, y):
            return x + y
        
        result = enforcer.check(pure_func, 2, 3)
        self.assertTrue(result.deterministic)
        self.assertEqual(result.output_hash, enforcer.hash_output(5))

    def test_non_deterministic_function_fails(self):
        enforcer = DeterminismEnforcer()
        call_count = [0]
        
        def impure_func():
            call_count[0] += 1
            return call_count[0]
        
        result = enforcer.check(impure_func)
        self.assertFalse(result.deterministic)

    def test_assert_deterministic_raises_on_failure(self):
        enforcer = DeterminismEnforcer()
        call_count = [0]
        
        def impure_func():
            call_count[0] += 1
            return call_count[0]
        
        with self.assertRaises(ValueError):
            enforcer.assert_deterministic(impure_func)


class TestAppendOnlyAuditEmitter(unittest.TestCase):
    def test_emit_and_verify_chain(self):
        emitter = AppendOnlyAuditEmitter()
        
        r1 = emitter.emit_record("module1", "event1", {"data": "test1"})
        r2 = emitter.emit_record("module1", "event2", {"data": "test2"})
        r3 = emitter.emit_record("module2", "event1", {"data": "test3"})
        
        self.assertEqual(r1.index, 0)
        self.assertEqual(r2.index, 1)
        self.assertEqual(r3.index, 2)
        
        # Verify chain
        valid, errors = emitter.verify_chain_integrity()
        self.assertTrue(valid)
        self.assertEqual(errors, [])

    def test_query_by_module(self):
        emitter = AppendOnlyAuditEmitter()
        emitter.emit_record("modA", "evt1", {})
        emitter.emit_record("modB", "evt1", {})
        emitter.emit_record("modA", "evt2", {})
        
        mod_a = emitter.query_by_module("modA")
        self.assertEqual(len(mod_a), 2)

    def test_query_by_time_range(self):
        emitter = AppendOnlyAuditEmitter()
        emitter.emit_record("mod", "evt1", {})
        time.sleep(0.01)
        emitter.emit_record("mod", "evt2", {})
        
        # Use UTC timezone-aware datetimes
        start = datetime.fromtimestamp(time.time() - 1, tz=timezone.utc)
        end = datetime.fromtimestamp(time.time() + 1, tz=timezone.utc)
        results = emitter.query_by_time_range(start, end)
        self.assertEqual(len(results), 2)


class TestCircuitBreaker(unittest.TestCase):
    def test_closed_to_open_on_failures(self):
        config = CircuitBreakerConfig(failure_threshold=3, timeout_seconds=1)
        cb = CircuitBreaker("test", config)
        
        def fail_func():
            raise ValueError("fail")
        
        # First 2 failures - should stay closed
        for _ in range(2):
            with self.assertRaises(ValueError):
                cb.call(fail_func)
            self.assertEqual(cb.state, CircuitState.CLOSED)
        
        # 3rd failure - should open
        with self.assertRaises(ValueError):
            cb.call(fail_func)
        self.assertEqual(cb.state, CircuitState.OPEN)

    def test_open_blocks_calls(self):
        config = CircuitBreakerConfig(failure_threshold=1, timeout_seconds=60)
        cb = CircuitBreaker("test", config)
        
        def fail_func():
            raise ValueError("fail")
        
        with self.assertRaises(ValueError):
            cb.call(fail_func)
        
        self.assertEqual(cb.state, CircuitState.OPEN)
        
        # Should block subsequent calls
        with self.assertRaises(CircuitOpenError):
            cb.call(lambda: "success")

    def test_half_open_after_timeout(self):
        config = CircuitBreakerConfig(failure_threshold=1, timeout_seconds=0.1, success_threshold=2)
        cb = CircuitBreaker("test", config)
        
        def fail_func():
            raise ValueError("fail")
        
        with self.assertRaises(ValueError):
            cb.call(fail_func)
        
        self.assertEqual(cb.state, CircuitState.OPEN)
        time.sleep(0.15)
        
        # Should transition to half-open
        self.assertEqual(cb.state, CircuitState.HALF_OPEN)

    def test_operator_force_close(self):
        config = CircuitBreakerConfig(failure_threshold=1, timeout_seconds=60)
        cb = CircuitBreaker("test", config)
        
        def fail_func():
            raise ValueError("fail")
        
        with self.assertRaises(ValueError):
            cb.call(fail_func)
        
        self.assertEqual(cb.state, CircuitState.OPEN)
        cb.force_closed("operator_1")
        self.assertEqual(cb.state, CircuitState.CLOSED)


class TestIdentityBoundaryEnforcer(unittest.TestCase):
    def test_create_and_isolate_contexts(self):
        enforcer = IdentityBoundaryEnforcer()
        
        ctx1 = enforcer.create_context("agent1")
        ctx2 = enforcer.create_context("agent2")
        
        enforcer.set_memory("agent1", "key", "value1")
        enforcer.set_memory("agent2", "key", "value2")
        
        self.assertEqual(enforcer.get_memory("agent1", "key"), "value1")
        self.assertEqual(enforcer.get_memory("agent2", "key"), "value2")

    def test_protected_identities(self):
        enforcer = IdentityBoundaryEnforcer()
        
        self.assertTrue(enforcer.is_protected("ARIS"))
        self.assertTrue(enforcer.is_protected("AAIS"))
        self.assertFalse(enforcer.is_protected("agent1"))

    def test_cannot_destroy_protected(self):
        enforcer = IdentityBoundaryEnforcer()
        
        with self.assertRaises(ValueError):
            enforcer.destroy_context("ARIS")


class TestIdentityLeakDetector(unittest.TestCase):
    def test_detects_memory_leaks(self):
        enforcer = IdentityBoundaryEnforcer()
        detector = IdentityLeakDetector(enforcer)
        
        enforcer.create_context("agent1")
        enforcer.create_context("agent2")
        enforcer.set_memory("agent1", "ref", "agent2")
        
        leaks = detector.scan_for_leaks()
        self.assertEqual(len(leaks), 1)
        self.assertEqual(leaks[0]["source_identity"], "agent1")
        self.assertEqual(leaks[0]["target_identity"], "agent2")


class TestDriftMonitor(unittest.TestCase):
    def test_records_observations(self):
        monitor = DriftMonitor("test_module")
        monitor.set_behavioral_baseline({"accuracy": 0.9})
        monitor.set_schema_baseline({"fields": ["a", "b"]})
        monitor.set_identity_baseline({"name": "test"})
        
        score = monitor.record_observation(
            behavioral={"accuracy": 0.85},
            schema={"fields": ["a", "b", "c"]},
            identity={"name": "test"},
        )
        
        self.assertGreater(score.behavioral, 0)
        self.assertGreater(score.schema, 0)
        self.assertEqual(score.identity, 0)

    def test_trend_detection(self):
        monitor = DriftMonitor("test_module")
        monitor.set_behavioral_baseline({"value": 1.0})
        
        # Record values moving away from baseline (increasing drift)
        for i in range(5):
            monitor.record_observation(behavioral={"value": 1.0 + i * 0.1})
        
        trend = monitor.get_trend(window=5)
        # Trend should be positive (drift increasing as values diverge from baseline)
        self.assertGreater(trend["behavioral"], 0, f"Expected positive trend, got {trend['behavioral']}")


class TestInterruptHandler(unittest.TestCase):
    def test_request_and_acknowledge(self):
        handler = InterruptHandler()
        
        req = InterruptRequest(
            reason=InterruptReason.OPERATOR_REQUEST,
            source="operator",
            target_module="test_module",
        )
        
        req_id = handler.request_interrupt(req)
        self.assertTrue(req_id)
        
        acked = handler.acknowledge(req_id)
        self.assertTrue(acked)
        
        pending = handler.get_pending()
        self.assertTrue(any(r.request_id == req_id and r.acknowledged for r in pending))


class TestKillSwitch(unittest.TestCase):
    def test_lockdown(self):
        ks = KillSwitch()
        
        self.assertFalse(ks.is_locked_down())
        
        ks.lockdown("test reason", "operator_1", {"diagnostic": "data"})
        
        self.assertTrue(ks.is_locked_down())
        self.assertTrue(ks.blocks("any_action"))

    def test_hard_kill(self):
        ks = KillSwitch()
        
        ks.hard_kill("critical", "operator_1", {})
        
        self.assertTrue(ks.is_hard_killed())
        self.assertTrue(ks.is_locked_down())

    def test_snapshot(self):
        ks = KillSwitch()
        ks.lockdown("reason", "operator", {})
        
        snap = ks.snapshot()
        self.assertTrue(snap.locked_down)
        self.assertEqual(snap.lockdown_reason, "reason")

    def test_operator_reset(self):
        ks = KillSwitch()
        ks.lockdown("reason", "operator", {})
        
        reset = ks.reset("operator_1")
        self.assertTrue(reset)
        self.assertFalse(ks.is_locked_down())


class TestSupremacyValidator(unittest.TestCase):
    def test_allows_valid_change(self):
        validator = SupremacyValidator()
        
        # Register a simple validator that always passes
        validator.register_validator("Λ.1", lambda c: ValidationReport(
            result=ValidationResult.ALLOWED,
            reason="OK",
        ))
        
        report = validator.validate({"change": "test"}, {})
        self.assertEqual(report.result, ValidationResult.ALLOWED)

    def test_rejects_invalid_change(self):
        validator = SupremacyValidator()
        
        validator.register_validator("Λ.1", lambda c: ValidationReport(
            result=ValidationResult.REJECTED,
            reason="Violation",
            violated_laws=["Λ.1"],
        ))
        
        report = validator.validate({"change": "test"}, {})
        self.assertEqual(report.result, ValidationResult.REJECTED)
        self.assertIn("Λ.1", report.violated_laws)

    def test_assert_valid_raises_on_rejection(self):
        validator = SupremacyValidator()
        
        validator.register_validator("Λ.1", lambda c: ValidationReport(
            result=ValidationResult.REJECTED,
            reason="Violation",
        ))
        
        with self.assertRaises(OverrideLockout):
            validator.assert_valid({"change": "test"}, {})

    def test_lockout_always_active(self):
        validator = SupremacyValidator()
        self.assertTrue(validator.lockout_active)
        # No disable method exists


if __name__ == "__main__":
    unittest.main()