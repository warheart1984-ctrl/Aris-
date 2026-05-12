"""
forge_eval.py — The admission gate.

Decides whether UL source is allowed to run, before any bytecode is compiled
or any VM frame is created.  Has no VM semantics.  Has no tracing semantics.
Only answers: "allowed?" + "why/why not?"

Pipeline:
    UL source
        ↓
    forge_eval.evaluate(source, rules, context)
        ↓
    EvalResult(allowed, violations, evidence)
        ↓
    if not allowed → GovernanceError (execution never happens)
        ↓
    compile → VM.run_code

Three layers of enforcement (v0):
    1. Hard-coded structural checks  — always on, not policy-configurable
    2. CompiledRule checks           — loaded from DSLSpec / policy files
    3. Context checks                — agent tier, scope, rate limits (stubs for now)
"""

from __future__ import annotations

import ast
import re
from dataclasses import dataclass, field
from typing import Any, Callable


# ── Core result types ─────────────────────────────────────────────────────────

@dataclass
class Violation:
    rule: str
    message: str
    severity: str = "HIGH"          # HIGH | MEDIUM | LOW
    location: tuple = ()            # (lineno, col_offset) when available
    evidence: str = ""              # excerpt or description


@dataclass
class EvalResult:
    allowed: bool
    violations: list[Violation] = field(default_factory=list)
    evidence: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict:
        return {
            "allowed": self.allowed,
            "violations": [
                {
                    "rule":     v.rule,
                    "message":  v.message,
                    "severity": v.severity,
                    "location": v.location,
                    "evidence": v.evidence,
                }
                for v in self.violations
            ],
            "evidence": self.evidence,
        }


class GovernanceError(Exception):
    def __init__(self, result: EvalResult):
        self.result = result
        msgs = "; ".join(v.message for v in result.violations)
        super().__init__(f"Governance gate blocked execution: {msgs}")


# ── CompiledRule — executable predicate over an AST ──────────────────────────

class CompiledRule:
    """
    A single compiled, executable law.

    In v0: predicate operates on UL source text (str) → list[Violation]
    In v1: will operate on typed UL AST nodes once those exist.

    Build via the rule-compiler helpers below or the DSLSpec compiler.
    """

    def __init__(self, name: str, predicate: Callable[[str], list[Violation]]):
        self.name = name
        self.predicate = predicate

    def check(self, source: str) -> list[Violation]:
        return self.predicate(source)


# ── Rule-compiler helpers (v0: text-pattern based) ───────────────────────────
#
# These operate on UL source text.  Once UL gains a typed AST (v1), these
# will be replaced with proper AST walkers.  The CompiledRule interface is
# identical either way — only the predicate implementation changes.

def forbid_pattern(rule_name: str, pattern: str, message: str = "") -> CompiledRule:
    """Block source containing a literal pattern."""
    msg = message or f"Forbidden pattern: {pattern!r}"
    def predicate(source: str) -> list[Violation]:
        if pattern in source:
            idx = source.index(pattern)
            line = source[:idx].count("\n") + 1
            return [Violation(rule=rule_name, message=msg,
                              location=(line, 0), evidence=pattern)]
        return []
    return CompiledRule(rule_name, predicate)


def forbid_call(rule_name: str, target: str, message: str = "",
                prefix_match: bool = False) -> CompiledRule:
    """Block calls to a named function (simple name match for v0)."""
    msg = message or f"Forbidden call: {target}()"
    # Match "target(" with optional whitespace — handles both direct call and call-in-expr
    pat = re.compile(r'\b' + re.escape(target) + r'\s*\(')
    def predicate(source: str) -> list[Violation]:
        m = pat.search(source)
        if m:
            line = source[:m.start()].count("\n") + 1
            return [Violation(rule=rule_name, message=msg,
                              location=(line, 0), evidence=m.group())]
        return []
    return CompiledRule(rule_name, predicate)


def forbid_import(rule_name: str, module: str, message: str = "") -> CompiledRule:
    """Block import of a module (UL doesn't have imports yet, but ready for when it does)."""
    msg = message or f"Forbidden import: {module}"
    pat = re.compile(r'\bimport\s+' + re.escape(module))
    def predicate(source: str) -> list[Violation]:
        m = pat.search(source)
        if m:
            line = source[:m.start()].count("\n") + 1
            return [Violation(rule=rule_name, message=msg, location=(line, 0))]
        return []
    return CompiledRule(rule_name, predicate)


def require_pattern(rule_name: str, pattern: str, message: str = "") -> CompiledRule:
    """Require source to contain a pattern."""
    msg = message or f"Required pattern missing: {pattern!r}"
    def predicate(source: str) -> list[Violation]:
        if pattern not in source:
            return [Violation(rule=rule_name, message=msg)]
        return []
    return CompiledRule(rule_name, predicate)


def max_lines(rule_name: str, limit: int) -> CompiledRule:
    """Reject programs longer than `limit` non-blank lines."""
    def predicate(source: str) -> list[Violation]:
        count = sum(1 for line in source.splitlines() if line.strip())
        if count > limit:
            return [Violation(rule=rule_name,
                              message=f"Program too long: {count} lines, max {limit}")]
        return []
    return CompiledRule(rule_name, predicate)


# Legacy alias kept for any callers using the old name
def forbid_node(rule_name: str, node_type_name: str, message: str = "") -> CompiledRule:
    """v0 stub — forbid_node will be meaningful once UL has typed AST nodes."""
    msg = message or f"Forbidden construct: {node_type_name}"
    # For now, match the name as a keyword in source
    return forbid_pattern(rule_name, node_type_name, msg)


# ── DSLSpec — parse a .dsl policy file into CompiledRules ────────────────────

class DSLSpec:
    """
    Minimal DSL parser.  Policy files look like:

        DSL v1
        NAMESPACE: ul_playground.sandbox

        LAW no_dangerous_call:
            forbid_call exec

        LAW no_infinite_loops:
            forbid_pattern "while true"

        LAW size_limit:
            max_lines 100

        LAW must_have_return:
            require_pattern "return"
    """

    VERSION = "v1"

    def __init__(self, text: str):
        self.text = text
        self.version: str = ""
        self.namespace: str = ""
        self.rules: list[CompiledRule] = []
        self._parse()

    def _parse(self):
        lines = self.text.splitlines()
        current_name: str | None = None

        for raw in lines:
            line = raw.strip()
            if not line or line.startswith("#"):
                continue
            if line.startswith("DSL "):
                self.version = line.split()[1]; continue
            if line.startswith("NAMESPACE:"):
                self.namespace = line.split(":", 1)[1].strip(); continue
            if line.startswith("LAW "):
                current_name = line.split()[1].rstrip(":"); continue
            if current_name is None:
                continue

            parts = line.split(None, 2)
            op = parts[0] if parts else ""

            if op == "forbid_call" and len(parts) >= 2:
                prefix = len(parts) >= 3 and parts[2] == "prefix"
                self.rules.append(forbid_call(current_name, parts[1], prefix_match=prefix))
            elif op == "forbid_pattern" and len(parts) >= 2:
                # strip optional quotes
                pat = parts[1].strip('"\'')
                self.rules.append(forbid_pattern(current_name, pat))
            elif op == "forbid_import" and len(parts) >= 2:
                self.rules.append(forbid_import(current_name, parts[1]))
            elif op == "require_pattern" and len(parts) >= 2:
                pat = parts[1].strip('"\'')
                self.rules.append(require_pattern(current_name, pat))
            elif op == "max_lines" and len(parts) >= 2:
                self.rules.append(max_lines(current_name, int(parts[1])))


# ── DocChannel — load and cache policy from file or text ─────────────────────

class DocChannel:
    """
    The canonical policy source.  Immutable once loaded.

    Usage:
        channel = DocChannel.from_file("policy/default.dsl")
        rules   = channel.compiled_rules
    """

    def __init__(self, text: str, source: str = "<inline>"):
        self.source = source
        self._spec = DSLSpec(text)
        self.namespace = self._spec.namespace
        self.version = self._spec.version

    @classmethod
    def from_file(cls, path: str) -> "DocChannel":
        with open(path) as f:
            return cls(f.read(), source=path)

    @classmethod
    def from_text(cls, text: str) -> "DocChannel":
        return cls(text, source="<inline>")

    @property
    def compiled_rules(self) -> list[CompiledRule]:
        return list(self._spec.rules)     # defensive copy


# ── ForgeEvaluator — the admission gate ──────────────────────────────────────

# Hard-coded structural rules that are always on regardless of policy.
# These protect the evaluation machinery itself.
_BUILTIN_RULES: list[CompiledRule] = [
    forbid_node("builtin:no_exec",   "AsyncFunctionDef",
                "Async functions not supported in UL substrate"),
]


class ForgeEvaluator:
    """
    The admission gate.

    evaluate(source, rules, context) → EvalResult
    fail-closed: if evaluation itself errors, returns blocked EvalResult.

    Typical usage:
        evaluator = ForgeEvaluator(doc_channel)
        result = evaluator.evaluate(source)
        if not result.allowed:
            raise GovernanceError(result)
        # ... compile + run
    """

    def __init__(self, channel: DocChannel | None = None):
        self._channel = channel
        self._extra_rules: list[CompiledRule] = []

    def add_rule(self, rule: CompiledRule):
        """Attach an ad-hoc rule (e.g. for testing or context-specific checks)."""
        self._extra_rules.append(rule)

    def evaluate(self, source: str, context: dict | None = None) -> EvalResult:
        ctx = context or {}

        # Fail-closed: if UL parsing explodes, that's a violation too
        try:
            from ul_core import tokenize as ul_tokenize, Parser as ULParser
            ul_tokens = ul_tokenize(source)
            ul_tree = ULParser(ul_tokens).parse()
        except (SyntaxError, Exception) as e:
            return EvalResult(
                allowed=False,
                violations=[Violation(
                    rule="forge:parse_error",
                    message=f"UL syntax error: {e}",
                )],
            )

        violations: list[Violation] = []

        # 1. Policy rules from DocChannel
        if self._channel:
            for rule in self._channel.compiled_rules:
                violations += rule.check(source)

        # 2. Extra rules (ad-hoc / context-specific)
        for rule in self._extra_rules:
            violations += rule.check(source)

        # 4. Build evidence summary — count UL AST nodes
        def _count_nodes(node, n=0):
            if isinstance(node, tuple):
                for child in node[1:]:
                    if isinstance(child, (tuple, list)):
                        for item in (child if isinstance(child, list) else [child]):
                            n = _count_nodes(item, n)
                n += 1
            return n

        node_count = _count_nodes(ul_tree)
        func_count = sum(1 for s in ul_tree[1] if isinstance(s, tuple) and s[0] == 'function')

        evidence = {
            "node_count":    node_count,
            "function_count": func_count,
            "namespace":     self._channel.namespace if self._channel else None,
            "policy_source": self._channel.source    if self._channel else None,
            "context":       ctx,
        }

        return EvalResult(
            allowed=len(violations) == 0,
            violations=violations,
            evidence=evidence,
        )

    def enforce(self, source: str, context: dict | None = None) -> EvalResult:
        """Evaluate and raise GovernanceError if blocked.  Convenience wrapper."""
        result = self.evaluate(source, context)
        if not result.allowed:
            raise GovernanceError(result)
        return result


# ── Default evaluator (no policy = UL parse check only) ──────────────────────

default_evaluator = ForgeEvaluator()

