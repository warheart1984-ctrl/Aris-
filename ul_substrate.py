"""
ul_substrate.py — Universal Language (Substrate Edition)

The AAIS governed command execution layer.

Where ul_lang.py is a general-purpose programming language,
ul_substrate.py is a governed command substrate. It does not compute —
it dispatches. Every expression is a governed action. The law is in the
grammar.

Grammar:
    Program     ::= Statement*
    Statement   ::= ActionStatement | BindStatement | CommentStatement
    Action      ::= Actor Verb Multiplier?
    Bind        ::= 'bind' Name 'to' Actor
    Multiplier  ::= 'x' INTEGER

Execution model:
    1. Tokenize source into tokens
    2. Parse into ActionAST nodes
    3. ForgeGate evaluates ALL nodes against capability table — fail closed
    4. If allowed, Dispatcher executes each action via registered handlers
    5. Every dispatch is logged to the SubstrateAuditLog

Design rules:
    - Governance is AST-native, not text-pattern based — no spoofing
    - Capability table is the single source of verb authority
    - Dispatch handlers are registered, not hardcoded — extensible
    - Every execution produces an AuditRecord — no silent operations
    - Fail-closed: unknown verb = blocked, not allowed
    - This file has zero general computation — loops, conditions, and
      arithmetic belong in ul_lang.py

For the AAIS playground and dev tooling, see ul_lang.py.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Callable, Dict, List, Optional
import re
import time


# ─────────────────────────────────────────────────────────────────────────────
# Capability Model
# ─────────────────────────────────────────────────────────────────────────────

class Capability:
    HARMLESS   = "harmless"    # no state change, no external effect
    QUERY      = "query"       # reads state, no mutation
    MUTATE     = "mutate"      # modifies local state
    DANGEROUS  = "dangerous"   # destructive or irreversible
    PRIVILEGED = "privileged"  # requires operator-level authorization


# Verb capability registry — the single source of verb authority.
# Unknown verbs are not in this table and are blocked by default.
#
# Extend this table to add new verbs. Do not infer capability from verb name.

VERB_CAPABILITIES: Dict[str, str] = {
    # Harmless
    "jumps":       Capability.HARMLESS,
    "runs":        Capability.HARMLESS,
    "meows":       Capability.HARMLESS,
    "pings":       Capability.HARMLESS,
    "greets":      Capability.HARMLESS,
    "logs":        Capability.HARMLESS,
    "echoes":      Capability.HARMLESS,

    # Query
    "reads":       Capability.QUERY,
    "inspects":    Capability.QUERY,
    "checks":      Capability.QUERY,
    "reports":     Capability.QUERY,
    "lists":       Capability.QUERY,
    "status":      Capability.QUERY,

    # Mutate
    "writes":      Capability.MUTATE,
    "updates":     Capability.MUTATE,
    "patches":     Capability.MUTATE,
    "registers":   Capability.MUTATE,
    "stores":      Capability.MUTATE,

    # Dangerous
    "deletes":     Capability.DANGEROUS,
    "removes":     Capability.DANGEROUS,
    "purges":      Capability.DANGEROUS,
    "shutdown":    Capability.DANGEROUS,
    "terminates":  Capability.DANGEROUS,
    "delete_repo": Capability.DANGEROUS,

    # Privileged
    "overrides":   Capability.PRIVILEGED,
    "escalates":   Capability.PRIVILEGED,
    "unlocks":     Capability.PRIVILEGED,
    "amends":      Capability.PRIVILEGED,
}


# ─────────────────────────────────────────────────────────────────────────────
# AST Nodes
# ─────────────────────────────────────────────────────────────────────────────

@dataclass(frozen=True)
class ActionNode:
    actor:      str
    verb:       str
    times:      int
    capability: str      # resolved at parse time from VERB_CAPABILITIES
    line:       int = 0


@dataclass(frozen=True)
class BindNode:
    alias: str
    actor: str
    line:  int = 0


@dataclass
class SubstrateProgram:
    statements: List[ActionNode | BindNode]


# ─────────────────────────────────────────────────────────────────────────────
# Tokenizer
# ─────────────────────────────────────────────────────────────────────────────

_SUBSTRATE_SPEC = [
    ('MULTIPLIER', r'x\d+'),          # x5, x10 — must come before NAME
    ('INTEGER',    r'\d+'),
    ('NAME',       r'[A-Za-z_][A-Za-z0-9_]*'),
    ('COMMENT',    r'#[^\n]*'),
    ('NEWLINE',    r'\n'),
    ('SKIP',       r'[ \t]+'),
    ('MISMATCH',   r'.'),
]
_SUB_RE = re.compile('|'.join('(?P<%s>%s)' % p for p in _SUBSTRATE_SPEC))


@dataclass
class SToken:
    type:  str
    value: str
    line:  int


def _tokenize(source: str) -> List[SToken]:
    tokens = []
    line   = 1
    for mo in _SUB_RE.finditer(source):
        kind = mo.lastgroup
        val  = mo.group()
        if kind in ('SKIP', 'COMMENT'):
            pass
        elif kind == 'NEWLINE':
            line += 1
        elif kind == 'MISMATCH':
            raise SyntaxError(f'Unexpected character {val!r} on line {line}')
        else:
            tokens.append(SToken(kind, val, line))
    tokens.append(SToken('EOF', '', line))
    return tokens


# ─────────────────────────────────────────────────────────────────────────────
# Parser
# ─────────────────────────────────────────────────────────────────────────────

class SubstrateParser:
    """
    Parses substrate source into a SubstrateProgram.
    Resolves verb capabilities at parse time.
    Unknown verbs produce a parse error — fail closed.
    """

    def __init__(self, tokens: List[SToken]):
        self.tokens = tokens
        self.pos    = 0

    def _peek(self) -> SToken:
        return self.tokens[self.pos]

    def _advance(self) -> SToken:
        t = self.tokens[self.pos]
        self.pos += 1
        return t

    def _expect(self, ttype: str, val: Optional[str] = None) -> SToken:
        t = self._peek()
        if t.type != ttype or (val is not None and t.value != val):
            raise SyntaxError(
                f'Line {t.line}: expected {ttype!r} {val!r}, got {t.type!r} {t.value!r}'
            )
        return self._advance()

    def parse(self) -> SubstrateProgram:
        stmts = []
        while self._peek().type != 'EOF':
            stmt = self._parse_statement()
            if stmt is not None:
                stmts.append(stmt)
        return SubstrateProgram(statements=stmts)

    def _parse_statement(self) -> Optional[ActionNode | BindNode]:
        t = self._peek()

        # bind alias to actor
        if t.type == 'NAME' and t.value == 'bind':
            return self._parse_bind()

        # ActionStatement: Actor Verb Multiplier?
        if t.type == 'NAME':
            return self._parse_action()

        raise SyntaxError(f'Line {t.line}: unexpected token {t.type!r} {t.value!r}')

    def _parse_bind(self) -> BindNode:
        line = self._peek().line
        self._expect('NAME', 'bind')
        alias = self._expect('NAME').value
        self._expect('NAME', 'to')
        actor = self._expect('NAME').value
        return BindNode(alias=alias, actor=actor, line=line)

    def _parse_action(self) -> ActionNode:
        actor_tok = self._advance()
        actor     = actor_tok.value
        line      = actor_tok.line

        if self._peek().type != 'NAME':
            raise SyntaxError(f'Line {line}: expected verb after actor {actor!r}')
        verb = self._advance().value

        # Capability resolution — unknown verb is a parse error, not a runtime error
        if verb not in VERB_CAPABILITIES:
            raise SyntaxError(
                f'Line {line}: unknown verb {verb!r} — '
                f'verbs must be declared in VERB_CAPABILITIES before use'
            )
        capability = VERB_CAPABILITIES[verb]

        # Optional multiplier
        times = 1
        if self._peek().type == 'MULTIPLIER':
            raw   = self._advance().value   # e.g. "x5"
            times = int(raw[1:])
            if times < 1:
                raise SyntaxError(f'Line {line}: multiplier must be >= 1, got {times}')

        return ActionNode(actor=actor, verb=verb, times=times,
                          capability=capability, line=line)


# ─────────────────────────────────────────────────────────────────────────────
# Governance Gate (ForgeGate)
# ─────────────────────────────────────────────────────────────────────────────

@dataclass
class GateViolation:
    rule:       str
    message:    str
    node:       ActionNode
    severity:   str = "HIGH"


@dataclass
class GateResult:
    allowed:    bool
    violations: List[GateViolation] = field(default_factory=list)

    def to_dict(self) -> dict:
        return {
            "allowed": self.allowed,
            "violations": [
                {
                    "rule":       v.rule,
                    "message":    v.message,
                    "severity":   v.severity,
                    "actor":      v.node.actor,
                    "verb":       v.node.verb,
                    "capability": v.node.capability,
                    "line":       v.node.line,
                }
                for v in self.violations
            ],
        }


class ForgeGate:
    """
    AST-native governance gate. Operates on ActionNode objects, not source text.
    Cannot be spoofed by whitespace or string manipulation.

    Usage:
        gate   = ForgeGate(blocked_capabilities={Capability.DANGEROUS})
        result = gate.evaluate(program)
        if not result.allowed:
            raise GovernanceError(result)
    """

    def __init__(
        self,
        blocked_capabilities: Optional[set] = None,
        require_operator_for:  Optional[set] = None,
        max_multiplier:        int = 100,
    ):
        self.blocked_capabilities  = blocked_capabilities or {
            Capability.DANGEROUS,
            Capability.PRIVILEGED,
        }
        self.require_operator_for  = require_operator_for or {
            Capability.PRIVILEGED,
        }
        self.max_multiplier        = max_multiplier

    def evaluate(
        self,
        program: SubstrateProgram,
        operator_present: bool = False,
    ) -> GateResult:
        violations: List[GateViolation] = []

        for stmt in program.statements:
            if not isinstance(stmt, ActionNode):
                continue

            # 1. Blocked capability check
            if stmt.capability in self.blocked_capabilities:
                violations.append(GateViolation(
                    rule    = "gate:blocked_capability",
                    message = (
                        f"Verb {stmt.verb!r} requires capability "
                        f"{stmt.capability!r} which is blocked by policy"
                    ),
                    node     = stmt,
                    severity = "CRITICAL" if stmt.capability == Capability.DANGEROUS else "HIGH",
                ))

            # 2. Privileged without operator
            if stmt.capability in self.require_operator_for and not operator_present:
                violations.append(GateViolation(
                    rule    = "gate:requires_operator",
                    message = (
                        f"Verb {stmt.verb!r} requires operator authorization "
                        f"(capability={stmt.capability!r})"
                    ),
                    node = stmt,
                ))

            # 3. Multiplier bound check
            if stmt.times > self.max_multiplier:
                violations.append(GateViolation(
                    rule    = "gate:multiplier_exceeded",
                    message = (
                        f"Multiplier x{stmt.times} exceeds maximum "
                        f"x{self.max_multiplier}"
                    ),
                    node = stmt,
                ))

        return GateResult(
            allowed    = len(violations) == 0,
            violations = violations,
        )


class GovernanceError(Exception):
    def __init__(self, result: GateResult):
        self.result = result
        msgs = "; ".join(v.message for v in result.violations)
        super().__init__(f"Governance gate blocked execution: {msgs}")


# ─────────────────────────────────────────────────────────────────────────────
# Audit Log
# ─────────────────────────────────────────────────────────────────────────────

@dataclass
class AuditRecord:
    timestamp:  float
    actor:      str
    verb:       str
    capability: str
    times:      int
    result:     str         # "dispatched" | "blocked" | "error"
    detail:     str = ""
    line:       int = 0

    def to_dict(self) -> dict:
        return {
            "timestamp":  self.timestamp,
            "actor":      self.actor,
            "verb":       self.verb,
            "capability": self.capability,
            "times":      self.times,
            "result":     self.result,
            "detail":     self.detail,
            "line":       self.line,
        }


class SubstrateAuditLog:
    """Append-only audit log. Every dispatch produces a record."""

    def __init__(self):
        self._records: List[AuditRecord] = []

    def record(self, **kwargs) -> AuditRecord:
        r = AuditRecord(timestamp=time.time(), **kwargs)
        self._records.append(r)
        return r

    @property
    def records(self) -> List[AuditRecord]:
        return list(self._records)  # defensive copy

    def to_list(self) -> List[dict]:
        return [r.to_dict() for r in self._records]


# ─────────────────────────────────────────────────────────────────────────────
# Dispatcher
# ─────────────────────────────────────────────────────────────────────────────

# Handler signature: (actor: str, verb: str, times: int, context: dict) -> Any
Handler = Callable[[str, str, int, Dict[str, Any]], Any]


class Dispatcher:
    """
    Routes governed actions to registered handlers.
    Handlers are registered per-verb. If no handler is registered,
    the action falls through to the default handler (logs and no-ops).

    This is where AAIS subsystem routing lives. Each subsystem registers
    its verbs here. The Dispatcher does not know what subsystems exist —
    it only routes.
    """

    def __init__(self):
        self._handlers: Dict[str, Handler] = {}
        self._default:  Optional[Handler]  = None

    def register(self, verb: str, handler: Handler):
        """Register a handler for a specific verb."""
        if verb not in VERB_CAPABILITIES:
            raise ValueError(
                f"Cannot register handler for unknown verb {verb!r} — "
                f"add it to VERB_CAPABILITIES first"
            )
        self._handlers[verb] = handler

    def set_default(self, handler: Handler):
        """Fallback handler for verbs with no registered handler."""
        self._default = handler

    def dispatch(
        self,
        node:    ActionNode,
        bindings: Dict[str, str],
        context: Dict[str, Any],
        audit:   SubstrateAuditLog,
    ) -> Any:
        """Dispatch a single ActionNode. Resolves actor aliases via bindings."""
        # Resolve actor alias
        actor = bindings.get(node.actor, node.actor)

        handler = self._handlers.get(node.verb, self._default)
        if handler is None:
            audit.record(
                actor=actor, verb=node.verb, capability=node.capability,
                times=node.times, result="error",
                detail=f"No handler registered for verb {node.verb!r}",
                line=node.line,
            )
            raise RuntimeError(
                f"No handler for verb {node.verb!r} — "
                f"register one via dispatcher.register({node.verb!r}, handler)"
            )

        try:
            result = handler(actor, node.verb, node.times, context)
            audit.record(
                actor=actor, verb=node.verb, capability=node.capability,
                times=node.times, result="dispatched",
                detail=str(result) if result is not None else "",
                line=node.line,
            )
            return result
        except Exception as e:
            audit.record(
                actor=actor, verb=node.verb, capability=node.capability,
                times=node.times, result="error", detail=str(e),
                line=node.line,
            )
            raise


# ─────────────────────────────────────────────────────────────────────────────
# Substrate Runtime — the public API
# ─────────────────────────────────────────────────────────────────────────────

@dataclass
class ExecutionResult:
    allowed:    bool
    gate:       GateResult
    audit:      List[dict]
    outputs:    List[Any]
    error:      Optional[str] = None

    def to_dict(self) -> dict:
        return {
            "allowed": self.allowed,
            "gate":    self.gate.to_dict(),
            "audit":   self.audit,
            "outputs": self.outputs,
            "error":   self.error,
        }


class SubstrateRuntime:
    """
    Full substrate pipeline:
        source → tokenize → parse → gate → dispatch → audit

    This is the integration point for AAIS subsystems.
    Instantiate once, register handlers, call execute() per request.
    """

    def __init__(
        self,
        gate:       Optional[ForgeGate]   = None,
        dispatcher: Optional[Dispatcher]  = None,
    ):
        self.gate       = gate       or ForgeGate()
        self.dispatcher = dispatcher or Dispatcher()
        self.audit      = SubstrateAuditLog()
        self._bindings: Dict[str, str] = {}

    def bind(self, alias: str, actor: str):
        """Bind an alias to an actor name. Applied to all subsequent executions."""
        self._bindings[alias] = actor

    def execute(
        self,
        source:           str,
        context:          Optional[Dict[str, Any]] = None,
        operator_present: bool = False,
    ) -> ExecutionResult:
        """
        Execute substrate source through the full governed pipeline.
        Returns ExecutionResult — never raises on governance failure.
        """
        ctx = context or {}

        # 1. Parse (unknown verbs are caught here — fail closed)
        try:
            tokens  = _tokenize(source)
            program = SubstrateParser(tokens).parse()
        except SyntaxError as e:
            gate_result = GateResult(allowed=False, violations=[
                GateViolation(
                    rule="gate:parse_error",
                    message=str(e),
                    node=ActionNode(actor="", verb="", times=0,
                                   capability="", line=0),
                )
            ])
            return ExecutionResult(
                allowed=False, gate=gate_result,
                audit=self.audit.to_list(), outputs=[], error=str(e),
            )

        # 2. Process bind statements
        for stmt in program.statements:
            if isinstance(stmt, BindNode):
                self._bindings[stmt.alias] = stmt.actor

        # 3. Governance gate — evaluate ALL actions before any dispatch
        actions = [s for s in program.statements if isinstance(s, ActionNode)]
        gate_result = self.gate.evaluate(
            SubstrateProgram(statements=actions),
            operator_present=operator_present,
        )

        if not gate_result.allowed:
            for stmt in actions:
                self.audit.record(
                    actor=stmt.actor, verb=stmt.verb,
                    capability=stmt.capability, times=stmt.times,
                    result="blocked",
                    detail="blocked by ForgeGate before dispatch",
                    line=stmt.line,
                )
            return ExecutionResult(
                allowed=False, gate=gate_result,
                audit=self.audit.to_list(), outputs=[],
            )

        # 4. Dispatch
        outputs = []
        try:
            for stmt in actions:
                result = self.dispatcher.dispatch(
                    node=stmt, bindings=self._bindings,
                    context=ctx, audit=self.audit,
                )
                outputs.append(result)
        except Exception as e:
            return ExecutionResult(
                allowed=True, gate=gate_result,
                audit=self.audit.to_list(), outputs=outputs,
                error=str(e),
            )

        return ExecutionResult(
            allowed=True, gate=gate_result,
            audit=self.audit.to_list(), outputs=outputs,
        )


# ─────────────────────────────────────────────────────────────────────────────
# Self-test
# ─────────────────────────────────────────────────────────────────────────────

if __name__ == '__main__':
    # --- Build runtime ---
    runtime = SubstrateRuntime()

    # Register handlers
    def _default_handler(actor, verb, times, context):
        msg = f"{actor}.{verb} x{times}"
        print(f"  → dispatch: {msg}")
        return msg

    def _reads_handler(actor, verb, times, context):
        result = f"{actor}.read() → [state_data]"
        print(f"  → query: {result}")
        return result

    runtime.dispatcher.set_default(_default_handler)
    runtime.dispatcher.register("reads", _reads_handler)

    # --- Test 1: allowed program ---
    print("=== Test 1: harmless + query actions ===")
    src1 = """\
cat jumps x3
repo reads
agent pings x1
"""
    r1 = runtime.execute(src1)
    print(f"allowed={r1.allowed}  audit_entries={len(r1.audit)}")
    assert r1.allowed

    # --- Test 2: blocked dangerous verb ---
    print("\n=== Test 2: dangerous verb (blocked) ===")
    src2 = """\
repo deletes x1
"""
    r2 = runtime.execute(src2)
    print(f"allowed={r2.allowed}")
    print(f"violation: {r2.gate.violations[0].message}")
    assert not r2.allowed

    # --- Test 3: bind alias ---
    print("\n=== Test 3: bind alias ===")
    src3 = """\
bind svc to agent
svc pings x2
"""
    r3 = runtime.execute(src3)
    print(f"allowed={r3.allowed}  outputs={r3.outputs}")
    assert r3.allowed

    # --- Test 4: unknown verb blocked at parse ---
    print("\n=== Test 4: unknown verb (parse error) ===")
    src4 = "cat flies x1"
    r4 = runtime.execute(src4)
    print(f"allowed={r4.allowed}  error={r4.error}")
    assert not r4.allowed

    print("\n=== All tests passed ===")
