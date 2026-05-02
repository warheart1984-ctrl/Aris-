from __future__ import annotations

import ast
from dataclasses import dataclass, field
from pathlib import Path
import re
import textwrap
from typing import Any, Iterable
import xml.etree.ElementTree as ET
import zipfile


DEFAULT_DOC_CHANNEL_TEXT = """
[GOAL]
Keep ARIS governed, deterministic, operator-facing, and verification-bound while coding and repo work remain inside law.

[LAWS]
- Never bypass UL or runtime law.
- No hidden path or unverified return.
- ARIS remains the speaking identity anchor.
- Evaluation feedback must remain structured and usable.

[GUIDELINES]
- Prefer small explicit functions and clear boundaries.
- Keep feedback tight and avoid bloated retry history.
- Treat laws as immutable during the loop.

[PATTERNS]
- pre_process -> core_aris_call -> post_process
- task -> generate -> execute -> evaluate -> learn -> repeat
- laws and fail conditions route to Disgrace-grade rejection

[FAIL]
- hidden path
- unverified return
- direct repo write outside governed mutation
- identity drift
- law bypass

[DSL]
DSL v1
NAMESPACE: aris.python
LAW no_global_state:
ast forbid Global
LAW no_random_import:
ast forbid_import "random"
LAW no_print:
ast forbid_call "print"
LAW no_subprocess:
ast forbid_import "subprocess"
LAW no_os_system:
ast forbid_call "os.system"
LAW no_eval:
ast forbid_call "eval"
LAW no_exec:
ast forbid_call "exec"
""".strip()


def _normalize_text(value: str) -> str:
    return re.sub(r"\s+", " ", str(value or "").strip())


def _strip_bullet(value: str) -> str:
    text = str(value or "").strip()
    if text.startswith("- "):
        return text[2:].strip()
    return text


def _quoted_values(text: str) -> list[str]:
    return re.findall(r'"([^"]+)"', str(text or ""))


@dataclass(frozen=True, slots=True)
class RuleSpec:
    name: str
    op: str
    target: str
    meta: dict[str, Any] = field(default_factory=dict)

    def payload(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "op": self.op,
            "target": self.target,
            "meta": dict(self.meta),
        }


@dataclass(frozen=True, slots=True)
class CompiledRule:
    name: str
    run: Any


@dataclass(frozen=True, slots=True)
class DocChannel:
    version: str
    namespace: str
    goal: str
    laws: tuple[str, ...] = ()
    guidelines: tuple[str, ...] = ()
    patterns: tuple[str, ...] = ()
    fail_conditions: tuple[str, ...] = ()
    dsl_text: str = ""
    rules: tuple[RuleSpec, ...] = ()
    metadata: dict[str, Any] = field(default_factory=dict)

    def payload(self) -> dict[str, Any]:
        return {
            "active": True,
            "version": self.version,
            "namespace": self.namespace,
            "goal": self.goal,
            "laws": list(self.laws),
            "guidelines": list(self.guidelines),
            "patterns": list(self.patterns),
            "fail_conditions": list(self.fail_conditions),
            "dsl_text": self.dsl_text,
            "rules": [rule.payload() for rule in self.rules],
            "metadata": dict(self.metadata),
        }

    def prompt_messages(self) -> list[dict[str, str]]:
        primary = [
            "ARIS DOC CHANNEL (IMMUTABLE)",
            f"Namespace: {self.namespace}",
            f"Version: {self.version}",
            f"Goal: {self.goal}",
            "SYSTEM LAW (NON-NEGOTIABLE):",
            *[f"- {item}" for item in self.laws],
            "FAIL CONDITIONS:",
            *[f"- {item}" for item in self.fail_conditions],
            "Instruction: Follow system law strictly. Violations are unacceptable.",
        ]
        secondary = [
            "ARIS DOC CHANNEL GUIDANCE",
            "GUIDELINES:",
            *[f"- {item}" for item in self.guidelines],
            "PATTERNS:",
            *[f"- {item}" for item in self.patterns],
        ]
        return [
            {"role": "system", "content": "\n".join(line for line in primary if line.strip())},
            {"role": "system", "content": "\n".join(line for line in secondary if line.strip())},
        ]

    def inject_messages(self, messages: Iterable[dict[str, str]]) -> list[dict[str, str]]:
        injected = [dict(message) for message in self.prompt_messages()]
        injected.extend(dict(message) for message in messages)
        return injected

    def evaluation_config_payload(self) -> dict[str, Any]:
        return {
            "doc_laws": list(self.laws),
            "doc_fail_conditions": list(self.fail_conditions),
            "doc_dsl": self.dsl_text,
            "doc_channel_version": self.version,
            "doc_channel_namespace": self.namespace,
        }


def extract_docx_text(path: Path) -> str:
    with zipfile.ZipFile(Path(path).expanduser().resolve()) as archive:
        xml = archive.read("word/document.xml")
    root = ET.fromstring(xml)
    namespace = {"w": "http://schemas.openxmlformats.org/wordprocessingml/2006/main"}
    parts: list[str] = []
    for paragraph in root.findall(".//w:p", namespace):
        text = "".join(node.text or "" for node in paragraph.findall(".//w:t", namespace)).strip()
        if text:
            parts.append(text)
    return "\n".join(parts)


def parse_doc_channel_text(text: str) -> DocChannel:
    sections: dict[str, list[str]] = {
        "GOAL": [],
        "LAWS": [],
        "GUIDELINES": [],
        "PATTERNS": [],
        "FAIL": [],
        "DSL": [],
    }
    current = ""
    for raw_line in str(text or "").splitlines():
        line = raw_line.rstrip()
        stripped = line.strip()
        if not stripped:
            continue
        if stripped.startswith("[") and stripped.endswith("]"):
            current = stripped[1:-1].strip().upper()
            sections.setdefault(current, [])
            continue
        if current == "GOAL":
            sections["GOAL"].append(stripped)
        elif current in {"LAWS", "GUIDELINES", "PATTERNS", "FAIL"}:
            sections[current].append(_strip_bullet(stripped))
        elif current == "DSL":
            sections["DSL"].append(stripped)

    dsl_text = "\n".join(sections["DSL"]).strip()
    version, namespace, rules = parse_doc_channel_dsl(dsl_text)
    goal = _normalize_text(" ".join(sections["GOAL"])) or "Governed ARIS operation."
    return DocChannel(
        version=version,
        namespace=namespace,
        goal=goal,
        laws=tuple(item for item in (_normalize_text(line) for line in sections["LAWS"]) if item),
        guidelines=tuple(
            item for item in (_normalize_text(line) for line in sections["GUIDELINES"]) if item
        ),
        patterns=tuple(item for item in (_normalize_text(line) for line in sections["PATTERNS"]) if item),
        fail_conditions=tuple(item for item in (_normalize_text(line) for line in sections["FAIL"]) if item),
        dsl_text=dsl_text,
        rules=rules,
        metadata={"source": "structured_text"},
    )


def default_doc_channel() -> DocChannel:
    return parse_doc_channel_text(DEFAULT_DOC_CHANNEL_TEXT)


def parse_doc_channel_dsl(dsl_text: str) -> tuple[str, str, tuple[RuleSpec, ...]]:
    version = "v1"
    namespace = "aris.python"
    current_rule = ""
    rules: list[RuleSpec] = []
    for raw_line in str(dsl_text or "").splitlines():
        line = raw_line.strip()
        if not line:
            continue
        if line.startswith("DSL "):
            version = _normalize_text(line[4:]) or version
            continue
        if line.startswith("NAMESPACE:"):
            namespace = _normalize_text(line.split(":", 1)[1]) or namespace
            continue
        if line.startswith("LAW ") and line.endswith(":"):
            current_rule = _normalize_text(line[4:-1])
            continue
        if not current_rule:
            continue
        if line.startswith("ast forbid_call "):
            values = _quoted_values(line)
            if values:
                rules.append(RuleSpec(name=current_rule, op="ast_forbid_call", target=values[0]))
            continue
        if line.startswith("ast require_call "):
            values = _quoted_values(line)
            if values:
                rules.append(RuleSpec(name=current_rule, op="ast_require_call", target=values[0]))
            continue
        if line.startswith("ast forbid_import "):
            values = _quoted_values(line)
            if values:
                rules.append(RuleSpec(name=current_rule, op="ast_forbid_import", target=values[0]))
            continue
        if line.startswith("ast forbid "):
            target = _normalize_text(line[len("ast forbid ") :])
            if target:
                rules.append(RuleSpec(name=current_rule, op="ast_forbid_node", target=target))
            continue
        arg_count_match = re.match(r'ast arg_count "([^"]+)"\s*(>=|==|<=)\s*(\d+)$', line)
        if arg_count_match:
            rules.append(
                RuleSpec(
                    name=current_rule,
                    op="arg_count",
                    target=arg_count_match.group(1),
                    meta={"op": arg_count_match.group(2), "value": int(arg_count_match.group(3))},
                )
            )
            continue
        arg_present_match = re.match(r'ast arg_present "([^"]+)"\s+"([^"]+)"$', line)
        if arg_present_match:
            rules.append(
                RuleSpec(
                    name=current_rule,
                    op="arg_present",
                    target=arg_present_match.group(1),
                    meta={"arg": arg_present_match.group(2)},
                )
            )
            continue
        forbid_arg_value_match = re.match(
            r'ast forbid_arg_value "([^"]+)"\s+"([^"]+)"\s+"([^"]+)"$',
            line,
        )
        if forbid_arg_value_match:
            rules.append(
                RuleSpec(
                    name=current_rule,
                    op="forbid_arg_value",
                    target=forbid_arg_value_match.group(1),
                    meta={
                        "arg": forbid_arg_value_match.group(2),
                        "value": forbid_arg_value_match.group(3),
                    },
                )
            )
    return version, namespace, tuple(rules)


def collect_aliases(tree: ast.AST) -> dict[str, str]:
    aliases: dict[str, str] = {}
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                local = alias.asname or alias.name.split(".")[0]
                aliases[local] = alias.name
        elif isinstance(node, ast.ImportFrom):
            module = node.module or ""
            for alias in node.names:
                local = alias.asname or alias.name
                aliases[local] = f"{module}.{alias.name}" if module else alias.name
    return aliases


def resolve_call_name(node: ast.AST, aliases: dict[str, str]) -> str | None:
    if isinstance(node, ast.Name):
        return aliases.get(node.id, node.id)
    if isinstance(node, ast.Attribute):
        parts: list[str] = []
        current: ast.AST = node
        while isinstance(current, ast.Attribute):
            parts.append(current.attr)
            current = current.value
        if isinstance(current, ast.Name):
            parts.append(aliases.get(current.id, current.id))
            return ".".join(reversed(parts))
    return None


def extract_call_args(node: ast.Call) -> tuple[list[ast.AST], dict[str, ast.AST]]:
    args = list(node.args)
    kwargs = {kw.arg: kw.value for kw in node.keywords if kw.arg}
    return args, kwargs


def resolve_literal(node: ast.AST) -> Any:
    if isinstance(node, ast.Constant):
        return node.value
    return None


def _violation(*, rule: RuleSpec, evidence: str) -> dict[str, Any]:
    return {
        "type": "LAW",
        "rule": rule.name,
        "operation": rule.op,
        "target": rule.target,
        "evidence": evidence,
    }


def compile_doc_channel_rules(rules: Iterable[RuleSpec]) -> tuple[CompiledRule, ...]:
    compiled: list[CompiledRule] = []
    for rule in rules:
        if rule.op == "ast_forbid_node":
            node_type = getattr(ast, rule.target, None)
            if node_type is None:
                continue

            def check(tree: ast.AST, spec: RuleSpec = rule, expected_type: Any = node_type) -> list[dict[str, Any]]:
                violations: list[dict[str, Any]] = []
                for node in ast.walk(tree):
                    if isinstance(node, expected_type):
                        violations.append(_violation(rule=spec, evidence=f"{spec.target} node found"))
                return violations

            compiled.append(CompiledRule(rule.name, check))
            continue
        if rule.op == "ast_forbid_call":
            def check(tree: ast.AST, spec: RuleSpec = rule) -> list[dict[str, Any]]:
                aliases = collect_aliases(tree)
                violations: list[dict[str, Any]] = []
                for node in ast.walk(tree):
                    if not isinstance(node, ast.Call):
                        continue
                    name = resolve_call_name(node.func, aliases)
                    if name == spec.target:
                        violations.append(_violation(rule=spec, evidence=f"{name}() call found"))
                return violations

            compiled.append(CompiledRule(rule.name, check))
            continue
        if rule.op == "ast_require_call":
            def check(tree: ast.AST, spec: RuleSpec = rule) -> list[dict[str, Any]]:
                aliases = collect_aliases(tree)
                for node in ast.walk(tree):
                    if isinstance(node, ast.Call) and resolve_call_name(node.func, aliases) == spec.target:
                        return []
                return [_violation(rule=spec, evidence=f"{spec.target}() not found")]

            compiled.append(CompiledRule(rule.name, check))
            continue
        if rule.op == "ast_forbid_import":
            def check(tree: ast.AST, spec: RuleSpec = rule) -> list[dict[str, Any]]:
                violations: list[dict[str, Any]] = []
                for node in ast.walk(tree):
                    if isinstance(node, ast.Import):
                        for alias in node.names:
                            if alias.name == spec.target:
                                violations.append(_violation(rule=spec, evidence=f"import {spec.target}"))
                    elif isinstance(node, ast.ImportFrom):
                        module = node.module or ""
                        if module == spec.target:
                            violations.append(_violation(rule=spec, evidence=f"from {spec.target} import ..."))
                return violations

            compiled.append(CompiledRule(rule.name, check))
            continue
        if rule.op == "arg_count":
            def check(tree: ast.AST, spec: RuleSpec = rule) -> list[dict[str, Any]]:
                aliases = collect_aliases(tree)
                violations: list[dict[str, Any]] = []
                expected_op = str(spec.meta.get("op", "=="))
                expected_value = int(spec.meta.get("value", 0))
                for node in ast.walk(tree):
                    if not isinstance(node, ast.Call):
                        continue
                    name = resolve_call_name(node.func, aliases)
                    if name != spec.target:
                        continue
                    args, _ = extract_call_args(node)
                    count = len(args)
                    ok = (
                        (expected_op == ">=" and count >= expected_value)
                        or (expected_op == "==" and count == expected_value)
                        or (expected_op == "<=" and count <= expected_value)
                    )
                    if not ok:
                        violations.append(
                            _violation(
                                rule=spec,
                                evidence=f"{name}() arg_count={count}, expected {expected_op} {expected_value}",
                            )
                        )
                return violations

            compiled.append(CompiledRule(rule.name, check))
            continue
        if rule.op == "arg_present":
            def check(tree: ast.AST, spec: RuleSpec = rule) -> list[dict[str, Any]]:
                aliases = collect_aliases(tree)
                violations: list[dict[str, Any]] = []
                expected_arg = str(spec.meta.get("arg", ""))
                for node in ast.walk(tree):
                    if not isinstance(node, ast.Call):
                        continue
                    name = resolve_call_name(node.func, aliases)
                    if name != spec.target:
                        continue
                    _, kwargs = extract_call_args(node)
                    if expected_arg not in kwargs:
                        violations.append(
                            _violation(
                                rule=spec,
                                evidence=f"{name}() missing arg '{expected_arg}'",
                            )
                        )
                return violations

            compiled.append(CompiledRule(rule.name, check))
            continue
        if rule.op == "forbid_arg_value":
            def check(tree: ast.AST, spec: RuleSpec = rule) -> list[dict[str, Any]]:
                aliases = collect_aliases(tree)
                violations: list[dict[str, Any]] = []
                expected_arg = str(spec.meta.get("arg", ""))
                forbidden = spec.meta.get("value")
                for node in ast.walk(tree):
                    if not isinstance(node, ast.Call):
                        continue
                    name = resolve_call_name(node.func, aliases)
                    if name != spec.target:
                        continue
                    _, kwargs = extract_call_args(node)
                    if expected_arg not in kwargs:
                        continue
                    value = resolve_literal(kwargs[expected_arg])
                    if value == forbidden:
                        violations.append(
                            _violation(
                                rule=spec,
                                evidence=f"{name}({expected_arg}={value}) forbidden",
                            )
                        )
                return violations

            compiled.append(CompiledRule(rule.name, check))
    return tuple(compiled)


def evaluate_program_against_doc_channel(program: str, doc_channel: DocChannel) -> list[dict[str, Any]]:
    if not doc_channel.rules:
        return []
    try:
        tree = ast.parse(textwrap.dedent(str(program or "")))
    except SyntaxError as exc:
        return [
            {
                "type": "SYNTAX",
                "rule": "invalid_python",
                "operation": "parse",
                "target": "python",
                "evidence": str(exc),
            }
        ]
    violations: list[dict[str, Any]] = []
    for rule in compile_doc_channel_rules(doc_channel.rules):
        violations.extend(rule.run(tree))
    return violations
