from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

from .config import NetworkShape
from .network import NeuralNetwork
from .tasks import TaskEvaluation

ProblemOutputKind = Literal["num", "bool"]
ExpressionKind = Literal["num", "bool"]
PhaseKind = Literal["temp", "return"]
RefKind = Literal["arg", "temp"]

_MAX_ARGS = 3
_TAG_ORDER = (
    "add",
    "sub",
    "mul",
    "max",
    "min",
    "abs",
    "mod",
    "eq",
    "gt",
    "lt",
    "logic",
    "condition",
    "clamp",
    "median",
    "between",
    "reuse",
)
_NUMERIC_ACTIONS = (
    "arg",
    "temp",
    "const_m2",
    "const_m1",
    "const0",
    "const1",
    "const2",
    "add",
    "sub",
    "mul",
    "max",
    "min",
    "abs",
    "neg",
    "mod2",
    "if",
)
_BOOLEAN_ACTIONS = (
    "eq",
    "gt",
    "lt",
    "and",
    "or",
    "not",
    "true",
    "false",
)
_SAFE_BUILTINS = {"abs": abs, "max": max, "min": min}


@dataclass(frozen=True, slots=True)
class CodeCase:
    inputs: tuple[float, ...]
    expected: float | bool


@dataclass(frozen=True, slots=True)
class CodeProblem:
    name: str
    prompt: str
    arg_names: tuple[str, ...]
    output_kind: ProblemOutputKind
    train_cases: tuple[CodeCase, ...]
    holdout_cases: tuple[CodeCase, ...]
    tags: dict[str, float]
    category: str
    difficulty: float
    weight: float

    def feature_vector(self, index: int, total: int) -> tuple[float, ...]:
        return (
            (index + 1) / max(total, 1),
            len(self.arg_names) / _MAX_ARGS,
            1.0 if self.output_kind == "bool" else 0.0,
            self.difficulty,
            *(self.tags.get(tag, 0.0) for tag in _TAG_ORDER),
        )


@dataclass(frozen=True, slots=True)
class BuildState:
    depth_remaining: int
    child_slot: int
    parent_kind: str
    total_nodes: int = 0
    numeric_nodes: int = 0
    boolean_nodes: int = 0
    statement_index: int = 0
    phase: PhaseKind = "return"
    available_temp_count: int = 0
    previous_terminal: float = 0.0

    def bump(self, kind: ExpressionKind, terminal: bool) -> "BuildState":
        return BuildState(
            depth_remaining=self.depth_remaining,
            child_slot=self.child_slot,
            parent_kind=self.parent_kind,
            total_nodes=self.total_nodes + 1,
            numeric_nodes=self.numeric_nodes + (1 if kind == "num" else 0),
            boolean_nodes=self.boolean_nodes + (1 if kind == "bool" else 0),
            statement_index=self.statement_index,
            phase=self.phase,
            available_temp_count=self.available_temp_count,
            previous_terminal=1.0 if terminal else 0.0,
        )

    def next_child(
        self,
        *,
        depth_remaining: int,
        child_slot: int,
        parent_kind: ExpressionKind,
    ) -> "BuildState":
        return BuildState(
            depth_remaining=depth_remaining,
            child_slot=child_slot,
            parent_kind=parent_kind,
            total_nodes=self.total_nodes,
            numeric_nodes=self.numeric_nodes,
            boolean_nodes=self.boolean_nodes,
            statement_index=self.statement_index,
            phase=self.phase,
            available_temp_count=self.available_temp_count,
            previous_terminal=self.previous_terminal,
        )

    def next_statement(
        self, *, statement_index: int, phase: PhaseKind, available_temp_count: int
    ) -> "BuildState":
        return BuildState(
            depth_remaining=self.depth_remaining,
            child_slot=0,
            parent_kind="root",
            total_nodes=self.total_nodes,
            numeric_nodes=self.numeric_nodes,
            boolean_nodes=self.boolean_nodes,
            statement_index=statement_index,
            phase=phase,
            available_temp_count=available_temp_count,
            previous_terminal=self.previous_terminal,
        )


@dataclass(frozen=True, slots=True)
class ControllerState:
    memory: tuple[float, ...]
    last_action_score: float = 0.0
    last_action_terminal: float = 0.0
    last_kind_num: float = 0.0
    last_kind_bool: float = 0.0


@dataclass(frozen=True, slots=True)
class Statement:
    index: int
    name: str
    expr: "ExprNode"


@dataclass(frozen=True, slots=True)
class ExprNode:
    kind: ExpressionKind
    op: str
    children: tuple["ExprNode", ...] = ()
    value: float | bool | None = None
    ref_kind: RefKind | None = None
    ref_index: int | None = None

    def render(self, arg_names: tuple[str, ...], temp_names: tuple[str, ...]) -> str:
        if self.op == "ref":
            if self.ref_kind == "arg":
                return arg_names[self.ref_index or 0]
            if self.ref_kind == "temp":
                return temp_names[self.ref_index or 0]
            raise ValueError("Reference node is missing a valid reference kind.")
        if self.op == "const":
            return repr(self.value)
        if self.op == "add":
            return f"({self.children[0].render(arg_names, temp_names)} + {self.children[1].render(arg_names, temp_names)})"
        if self.op == "sub":
            return f"({self.children[0].render(arg_names, temp_names)} - {self.children[1].render(arg_names, temp_names)})"
        if self.op == "mul":
            return f"({self.children[0].render(arg_names, temp_names)} * {self.children[1].render(arg_names, temp_names)})"
        if self.op == "max":
            return f"max({self.children[0].render(arg_names, temp_names)}, {self.children[1].render(arg_names, temp_names)})"
        if self.op == "min":
            return f"min({self.children[0].render(arg_names, temp_names)}, {self.children[1].render(arg_names, temp_names)})"
        if self.op == "abs":
            return f"abs({self.children[0].render(arg_names, temp_names)})"
        if self.op == "neg":
            return f"(-{self.children[0].render(arg_names, temp_names)})"
        if self.op == "mod2":
            return f"({self.children[0].render(arg_names, temp_names)} % 2)"
        if self.op == "if":
            return (
                f"({self.children[1].render(arg_names, temp_names)} if "
                f"{self.children[0].render(arg_names, temp_names)} else "
                f"{self.children[2].render(arg_names, temp_names)})"
            )
        if self.op == "eq":
            return f"({self.children[0].render(arg_names, temp_names)} == {self.children[1].render(arg_names, temp_names)})"
        if self.op == "gt":
            return f"({self.children[0].render(arg_names, temp_names)} > {self.children[1].render(arg_names, temp_names)})"
        if self.op == "lt":
            return f"({self.children[0].render(arg_names, temp_names)} < {self.children[1].render(arg_names, temp_names)})"
        if self.op == "and":
            return f"({self.children[0].render(arg_names, temp_names)} and {self.children[1].render(arg_names, temp_names)})"
        if self.op == "or":
            return f"({self.children[0].render(arg_names, temp_names)} or {self.children[1].render(arg_names, temp_names)})"
        if self.op == "not":
            return f"(not {self.children[0].render(arg_names, temp_names)})"
        raise ValueError(f"Unsupported expression op: {self.op}")

    def node_count(self) -> int:
        return 1 + sum(child.node_count() for child in self.children)

    def op_counts(self) -> dict[str, int]:
        counts: dict[str, int] = {self.op: 1}
        for child in self.children:
            for name, count in child.op_counts().items():
                counts[name] = counts.get(name, 0) + count
        return counts

    def referenced_temps(self) -> set[int]:
        found: set[int] = set()
        if self.op == "ref" and self.ref_kind == "temp" and self.ref_index is not None:
            found.add(self.ref_index)
        for child in self.children:
            found.update(child.referenced_temps())
        return found


@dataclass(frozen=True, slots=True)
class ProgramArtifact:
    problem: CodeProblem
    statements: tuple[Statement, ...]
    root: ExprNode
    source_code: str
    node_count: int
    line_count: int

    def compile(self):
        globals_scope = {"__builtins__": _SAFE_BUILTINS.copy()}
        locals_scope: dict[str, object] = {}
        exec(self.source_code, globals_scope, locals_scope)
        return locals_scope[self.problem.name]


@dataclass(frozen=True, slots=True)
class ProgramScore:
    artifact: ProgramArtifact
    train_score: float
    holdout_score: float
    train_pass_rate: float
    holdout_pass_rate: float
    exact_solution: float


@dataclass(frozen=True, slots=True)
class ControllerDecision:
    action: str
    next_state: ControllerState
    reference_index: int | None = None
    action_score: float = 0.0


@dataclass(frozen=True, slots=True)
class RecurrentCodeController:
    memory_size: int
    reference_slots: int

    @property
    def output_size(self) -> int:
        return (
            len(_NUMERIC_ACTIONS)
            + len(_BOOLEAN_ACTIONS)
            + self.reference_slots
            + (self.memory_size * 2)
        )

    def initial_state(self) -> ControllerState:
        return ControllerState(memory=(0.0,) * self.memory_size)

    def decide(
        self,
        network: NeuralNetwork,
        features: tuple[float, ...],
        state: ControllerState,
        kind: ExpressionKind,
        allowed_actions: tuple[str, ...],
        arg_count: int,
        temp_count: int,
    ) -> ControllerDecision:
        outputs = network.predict(features)
        numeric_end = len(_NUMERIC_ACTIONS)
        boolean_end = numeric_end + len(_BOOLEAN_ACTIONS)
        reference_end = boolean_end + self.reference_slots
        action_space = _NUMERIC_ACTIONS if kind == "num" else _BOOLEAN_ACTIONS
        scores = outputs[:numeric_end] if kind == "num" else outputs[numeric_end:boolean_end]
        best_action = allowed_actions[0]
        best_score = float("-inf")
        for index, action in enumerate(action_space):
            if action in allowed_actions and scores[index] > best_score:
                best_action = action
                best_score = scores[index]

        reference_index: int | None = None
        reference_scores = outputs[boolean_end:reference_end]
        if best_action == "arg":
            reference_index = self._choose_reference(reference_scores, 0, arg_count)
        elif best_action == "temp":
            reference_index = self._choose_reference(
                reference_scores,
                _MAX_ARGS,
                temp_count,
            )

        proposal = outputs[reference_end : reference_end + self.memory_size]
        gates = outputs[
            reference_end + self.memory_size : reference_end + (self.memory_size * 2)
        ]
        next_memory = tuple(
            (((gate + 1.0) / 2.0) * old_value)
            + ((1.0 - ((gate + 1.0) / 2.0)) * proposal[index])
            for index, (old_value, gate) in enumerate(zip(state.memory, gates))
        )
        terminal = best_action in {
            "arg",
            "temp",
            "const_m2",
            "const_m1",
            "const0",
            "const1",
            "const2",
            "true",
            "false",
        }
        return ControllerDecision(
            action=best_action,
            reference_index=reference_index,
            action_score=best_score,
            next_state=ControllerState(
                memory=next_memory,
                last_action_score=max(-1.0, min(1.0, best_score)),
                last_action_terminal=1.0 if terminal else 0.0,
                last_kind_num=1.0 if kind == "num" else 0.0,
                last_kind_bool=1.0 if kind == "bool" else 0.0,
            ),
        )

    def _choose_reference(
        self, reference_scores: tuple[float, ...], offset: int, count: int
    ) -> int:
        if count <= 0:
            return 0
        best_index = 0
        best_score = float("-inf")
        for index in range(count):
            score = reference_scores[offset + index]
            if score > best_score:
                best_index = index
                best_score = score
        return best_index


@dataclass(frozen=True, slots=True)
class CodeWritingBenchmarkTask:
    hidden_layers: tuple[int, ...] = (48, 32, 24)
    max_depth: int = 5
    max_nodes: int = 18
    temp_slots: int = 2
    memory_size: int = 8
    name: str = "code-agent"

    def __post_init__(self) -> None:
        if self.temp_slots < 1:
            raise ValueError("temp_slots must be at least 1.")
        if self.memory_size < 1:
            raise ValueError("memory_size must be at least 1.")
        if self.max_depth < 2:
            raise ValueError("max_depth must be at least 2.")
        if self.max_nodes < 6:
            raise ValueError("max_nodes must be at least 6.")

    @property
    def controller(self) -> RecurrentCodeController:
        return RecurrentCodeController(
            memory_size=self.memory_size,
            reference_slots=_MAX_ARGS + self.temp_slots,
        )

    @property
    def input_size(self) -> int:
        problem_features = 4 + len(_TAG_ORDER)
        build_features = 15
        controller_summary = 4
        return problem_features + build_features + controller_summary + self.memory_size

    @property
    def shape(self) -> NetworkShape:
        return NetworkShape(
            input_size=self.input_size,
            hidden_layers=self.hidden_layers,
            output_size=self.controller.output_size,
            activation="tanh",
            output_activation="tanh",
        )

    @property
    def problems(self) -> tuple[CodeProblem, ...]:
        return _ADVANCED_PROBLEMS

    def _feature_vector(
        self,
        *,
        problem: CodeProblem,
        problem_index: int,
        requested_kind: ExpressionKind,
        build_state: BuildState,
        controller_state: ControllerState,
    ) -> tuple[float, ...]:
        return (
            *problem.feature_vector(problem_index, len(self.problems)),
            1.0 if requested_kind == "num" else 0.0,
            1.0 if requested_kind == "bool" else 0.0,
            build_state.depth_remaining / max(self.max_depth, 1),
            build_state.child_slot / 3.0,
            build_state.total_nodes / max(self.max_nodes, 1),
            build_state.numeric_nodes / max(self.max_nodes, 1),
            build_state.boolean_nodes / max(self.max_nodes, 1),
            build_state.statement_index / max(self.temp_slots, 1),
            1.0 if build_state.phase == "temp" else 0.0,
            1.0 if build_state.phase == "return" else 0.0,
            build_state.available_temp_count / max(self.temp_slots, 1),
            1.0 if build_state.parent_kind == "num" else 0.0,
            1.0 if build_state.parent_kind == "bool" else 0.0,
            1.0 if build_state.parent_kind == "root" else 0.0,
            build_state.previous_terminal,
            controller_state.last_action_score,
            controller_state.last_action_terminal,
            controller_state.last_kind_num,
            controller_state.last_kind_bool,
            *controller_state.memory,
        )

    def _numeric_allowed(self, state: BuildState) -> tuple[str, ...]:
        nodes_left = self.max_nodes - state.total_nodes
        allowed: list[str] = [
            "arg",
            "const_m2",
            "const_m1",
            "const0",
            "const1",
            "const2",
        ]
        if state.available_temp_count > 0:
            allowed.insert(1, "temp")
        if state.depth_remaining <= 0 or nodes_left <= 1:
            return tuple(allowed)
        allowed.extend(["abs", "neg", "mod2"])
        if nodes_left >= 3:
            allowed.extend(["add", "sub", "mul", "max", "min"])
        if nodes_left >= 4:
            allowed.append("if")
        return tuple(allowed)

    def _boolean_allowed(self, state: BuildState) -> tuple[str, ...]:
        nodes_left = self.max_nodes - state.total_nodes
        allowed: list[str] = ["true", "false"]
        if state.depth_remaining <= 0 or nodes_left <= 1:
            return tuple(allowed)
        allowed.append("not")
        if nodes_left >= 3:
            allowed.extend(["eq", "gt", "lt", "and", "or"])
        return tuple(allowed)

    def _constant_value(self, action: str) -> float:
        return {
            "const_m2": -2.0,
            "const_m1": -1.0,
            "const0": 0.0,
            "const1": 1.0,
            "const2": 2.0,
        }[action]

    def _build_numeric(
        self,
        network: NeuralNetwork,
        problem: CodeProblem,
        problem_index: int,
        build_state: BuildState,
        controller_state: ControllerState,
    ) -> tuple[ExprNode, BuildState, ControllerState]:
        decision = self.controller.decide(
            network=network,
            features=self._feature_vector(
                problem=problem,
                problem_index=problem_index,
                requested_kind="num",
                build_state=build_state,
                controller_state=controller_state,
            ),
            state=controller_state,
            kind="num",
            allowed_actions=self._numeric_allowed(build_state),
            arg_count=len(problem.arg_names),
            temp_count=build_state.available_temp_count,
        )
        action = decision.action
        if action == "arg":
            return (
                ExprNode(
                    kind="num",
                    op="ref",
                    ref_kind="arg",
                    ref_index=decision.reference_index,
                ),
                build_state.bump("num", terminal=True),
                decision.next_state,
            )
        if action == "temp":
            return (
                ExprNode(
                    kind="num",
                    op="ref",
                    ref_kind="temp",
                    ref_index=decision.reference_index,
                ),
                build_state.bump("num", terminal=True),
                decision.next_state,
            )
        if action.startswith("const"):
            return (
                ExprNode(kind="num", op="const", value=self._constant_value(action)),
                build_state.bump("num", terminal=True),
                decision.next_state,
            )

        current_state = build_state.bump("num", terminal=False)
        depth = max(0, build_state.depth_remaining - 1)
        if action in {"abs", "neg", "mod2"}:
            child, next_build_state, next_controller_state = self._build_numeric(
                network,
                problem,
                problem_index,
                current_state.next_child(
                    depth_remaining=depth,
                    child_slot=0,
                    parent_kind="num",
                ),
                decision.next_state,
            )
            return (
                ExprNode(kind="num", op=action, children=(child,)),
                next_build_state,
                next_controller_state,
            )
        if action == "if":
            condition, after_condition, condition_controller = self._build_boolean(
                network,
                problem,
                problem_index,
                current_state.next_child(
                    depth_remaining=depth,
                    child_slot=0,
                    parent_kind="num",
                ),
                decision.next_state,
            )
            when_true, after_true, true_controller = self._build_numeric(
                network,
                problem,
                problem_index,
                after_condition.next_child(
                    depth_remaining=depth,
                    child_slot=1,
                    parent_kind="num",
                ),
                condition_controller,
            )
            when_false, after_false, false_controller = self._build_numeric(
                network,
                problem,
                problem_index,
                after_true.next_child(
                    depth_remaining=depth,
                    child_slot=2,
                    parent_kind="num",
                ),
                true_controller,
            )
            return (
                ExprNode(
                    kind="num",
                    op="if",
                    children=(condition, when_true, when_false),
                ),
                after_false,
                false_controller,
            )

        left, after_left, left_controller = self._build_numeric(
            network,
            problem,
            problem_index,
            current_state.next_child(
                depth_remaining=depth,
                child_slot=0,
                parent_kind="num",
            ),
            decision.next_state,
        )
        right, after_right, right_controller = self._build_numeric(
            network,
            problem,
            problem_index,
            after_left.next_child(
                depth_remaining=depth,
                child_slot=1,
                parent_kind="num",
            ),
            left_controller,
        )
        return (
            ExprNode(kind="num", op=action, children=(left, right)),
            after_right,
            right_controller,
        )

    def _build_boolean(
        self,
        network: NeuralNetwork,
        problem: CodeProblem,
        problem_index: int,
        build_state: BuildState,
        controller_state: ControllerState,
    ) -> tuple[ExprNode, BuildState, ControllerState]:
        decision = self.controller.decide(
            network=network,
            features=self._feature_vector(
                problem=problem,
                problem_index=problem_index,
                requested_kind="bool",
                build_state=build_state,
                controller_state=controller_state,
            ),
            state=controller_state,
            kind="bool",
            allowed_actions=self._boolean_allowed(build_state),
            arg_count=len(problem.arg_names),
            temp_count=build_state.available_temp_count,
        )
        action = decision.action
        if action == "true":
            return (
                ExprNode(kind="bool", op="const", value=True),
                build_state.bump("bool", terminal=True),
                decision.next_state,
            )
        if action == "false":
            return (
                ExprNode(kind="bool", op="const", value=False),
                build_state.bump("bool", terminal=True),
                decision.next_state,
            )

        current_state = build_state.bump("bool", terminal=False)
        depth = max(0, build_state.depth_remaining - 1)
        if action == "not":
            child, next_build_state, next_controller_state = self._build_boolean(
                network,
                problem,
                problem_index,
                current_state.next_child(
                    depth_remaining=depth,
                    child_slot=0,
                    parent_kind="bool",
                ),
                decision.next_state,
            )
            return (
                ExprNode(kind="bool", op="not", children=(child,)),
                next_build_state,
                next_controller_state,
            )
        if action in {"and", "or"}:
            left, after_left, left_controller = self._build_boolean(
                network,
                problem,
                problem_index,
                current_state.next_child(
                    depth_remaining=depth,
                    child_slot=0,
                    parent_kind="bool",
                ),
                decision.next_state,
            )
            right, after_right, right_controller = self._build_boolean(
                network,
                problem,
                problem_index,
                after_left.next_child(
                    depth_remaining=depth,
                    child_slot=1,
                    parent_kind="bool",
                ),
                left_controller,
            )
            return (
                ExprNode(kind="bool", op=action, children=(left, right)),
                after_right,
                right_controller,
            )

        left, after_left, left_controller = self._build_numeric(
            network,
            problem,
            problem_index,
            current_state.next_child(
                depth_remaining=depth,
                child_slot=0,
                parent_kind="bool",
            ),
            decision.next_state,
        )
        right, after_right, right_controller = self._build_numeric(
            network,
            problem,
            problem_index,
            after_left.next_child(
                depth_remaining=depth,
                child_slot=1,
                parent_kind="bool",
            ),
            left_controller,
        )
        return (
            ExprNode(kind="bool", op=action, children=(left, right)),
            after_right,
            right_controller,
        )

    def _prune_statements(
        self, statements: tuple[Statement, ...], root: ExprNode
    ) -> tuple[Statement, ...]:
        needed = root.referenced_temps()
        emitted: list[Statement] = []
        for statement in reversed(statements):
            if statement.index not in needed:
                continue
            emitted.append(statement)
            needed.remove(statement.index)
            needed.update(statement.expr.referenced_temps())
        emitted.reverse()
        return tuple(emitted)

    def _build_artifact(
        self, network: NeuralNetwork, problem: CodeProblem, problem_index: int
    ) -> ProgramArtifact:
        controller_state = self.controller.initial_state()
        base_state = BuildState(
            depth_remaining=self.max_depth,
            child_slot=0,
            parent_kind="root",
        )
        temp_names = tuple(f"tmp{index}" for index in range(self.temp_slots))
        raw_statements: list[Statement] = []
        running_state = base_state

        for temp_index, temp_name in enumerate(temp_names):
            temp_state = running_state.next_statement(
                statement_index=temp_index,
                phase="temp",
                available_temp_count=temp_index,
            )
            expr, running_state, controller_state = self._build_numeric(
                network,
                problem,
                problem_index,
                temp_state,
                controller_state,
            )
            raw_statements.append(Statement(index=temp_index, name=temp_name, expr=expr))

        root_state = running_state.next_statement(
            statement_index=self.temp_slots,
            phase="return",
            available_temp_count=self.temp_slots,
        )
        if problem.output_kind == "bool":
            root, final_state, _ = self._build_boolean(
                network,
                problem,
                problem_index,
                root_state,
                controller_state,
            )
        else:
            root, final_state, _ = self._build_numeric(
                network,
                problem,
                problem_index,
                root_state,
                controller_state,
            )

        emitted = self._prune_statements(tuple(raw_statements), root)
        lines = [f"def {problem.name}({', '.join(problem.arg_names)}):"]
        for statement in emitted:
            rendered = statement.expr.render(problem.arg_names, temp_names)
            lines.append(f"    {statement.name} = {rendered}")
        lines.append(f"    return {root.render(problem.arg_names, temp_names)}")
        node_count = root.node_count() + sum(
            statement.expr.node_count() for statement in emitted
        )
        return ProgramArtifact(
            problem=problem,
            statements=emitted,
            root=root,
            source_code="\n".join(lines) + "\n",
            node_count=min(node_count, final_state.total_nodes),
            line_count=1 + len(emitted),
        )

    def _case_score(self, actual: object, expected: float | bool) -> tuple[float, float]:
        if isinstance(expected, bool):
            if isinstance(actual, bool):
                match = 1.0 if actual is expected else 0.0
                return match, match
            if isinstance(actual, (int, float)):
                distance = abs(float(actual) - float(expected))
                return (1.0 / (1.0 + distance), 1.0 if bool(actual) is expected else 0.0)
            return (0.0, 0.0)

        if isinstance(actual, bool):
            actual_value = float(actual)
        elif isinstance(actual, (int, float)):
            actual_value = float(actual)
        else:
            return (0.0, 0.0)
        distance = abs(actual_value - float(expected))
        exact = 1.0 if distance <= 1e-6 else 0.0
        return (1.0 / (1.0 + distance), exact)

    def _score_cases(self, function, cases: tuple[CodeCase, ...]) -> tuple[float, float]:
        smooth_total = 0.0
        exact_total = 0.0
        for case in cases:
            try:
                actual = function(*case.inputs)
            except Exception:
                actual = None
            smooth, exact = self._case_score(actual, case.expected)
            smooth_total += smooth
            exact_total += exact
        count = max(len(cases), 1)
        return smooth_total / count, exact_total / count

    def _evaluate_artifact(self, artifact: ProgramArtifact) -> ProgramScore:
        try:
            function = artifact.compile()
        except Exception:
            return ProgramScore(
                artifact=artifact,
                train_score=0.0,
                holdout_score=0.0,
                train_pass_rate=0.0,
                holdout_pass_rate=0.0,
                exact_solution=0.0,
            )

        train_score, train_pass_rate = self._score_cases(function, artifact.problem.train_cases)
        holdout_score, holdout_pass_rate = self._score_cases(function, artifact.problem.holdout_cases)
        return ProgramScore(
            artifact=artifact,
            train_score=train_score,
            holdout_score=holdout_score,
            train_pass_rate=train_pass_rate,
            holdout_pass_rate=holdout_pass_rate,
            exact_solution=1.0 if holdout_pass_rate == 1.0 else 0.0,
        )

    def _problem_objective(self, problem: CodeProblem, score: ProgramScore) -> float:
        base = (
            0.18 * score.train_score
            + 0.47 * score.holdout_score
            + 0.10 * score.train_pass_rate
            + 0.25 * score.holdout_pass_rate
            + (0.05 * score.exact_solution)
        )
        complexity_penalty = max(
            0.0,
            score.artifact.node_count - (4 + score.artifact.line_count),
        ) * 0.01
        line_penalty = max(0.0, score.artifact.line_count - 1) * 0.015
        return max(
            0.0,
            min(
                1.0,
                (base - complexity_penalty - line_penalty) * problem.difficulty,
            ),
        )

    def evaluate(self, network: NeuralNetwork) -> TaskEvaluation:
        problem_scores: list[tuple[CodeProblem, ProgramScore]] = []
        for index, problem in enumerate(self.problems):
            artifact = self._build_artifact(network, problem, index)
            problem_scores.append((problem, self._evaluate_artifact(artifact)))

        total_weight = sum(problem.weight for problem, _ in problem_scores)
        weighted_objective = sum(
            self._problem_objective(problem, score) * problem.weight
            for problem, score in problem_scores
        ) / total_weight
        weighted_exact_rate = sum(
            score.exact_solution * problem.weight for problem, score in problem_scores
        ) / total_weight
        weighted_holdout = sum(
            score.holdout_pass_rate * problem.weight for problem, score in problem_scores
        ) / total_weight
        objective = min(
            1.0,
            weighted_objective + (0.08 * weighted_exact_rate) + (0.04 * weighted_holdout),
        )

        diagnostics = {
            "average_train_score": sum(score.train_score for _, score in problem_scores)
            / len(problem_scores),
            "average_holdout_score": sum(score.holdout_score for _, score in problem_scores)
            / len(problem_scores),
            "average_holdout_pass_rate": sum(
                score.holdout_pass_rate for _, score in problem_scores
            )
            / len(problem_scores),
            "weighted_exact_rate": weighted_exact_rate,
            "problems_solved": sum(score.exact_solution for _, score in problem_scores),
            "suite_solved": 1.0
            if all(score.exact_solution == 1.0 for _, score in problem_scores)
            else 0.0,
            "average_node_count": sum(score.artifact.node_count for _, score in problem_scores)
            / len(problem_scores),
            "average_line_count": sum(score.artifact.line_count for _, score in problem_scores)
            / len(problem_scores),
        }

        category_totals: dict[str, float] = {}
        category_weights: dict[str, float] = {}
        family_names = (
            "ref",
            "const",
            "add",
            "sub",
            "mul",
            "max",
            "min",
            "abs",
            "mod2",
            "if",
            "eq",
            "gt",
            "lt",
            "and",
            "or",
            "not",
        )
        family_counts = {name: 0 for name in family_names}
        behavior: list[float] = []

        for problem, score in problem_scores:
            behavior.extend(
                (
                    score.train_score,
                    score.holdout_score,
                    score.holdout_pass_rate,
                    score.exact_solution,
                    min(1.0, score.artifact.node_count / self.max_nodes),
                    min(1.0, score.artifact.line_count / (self.temp_slots + 1)),
                )
            )
            category_totals[problem.category] = category_totals.get(problem.category, 0.0) + (
                score.holdout_pass_rate * problem.weight
            )
            category_weights[problem.category] = category_weights.get(problem.category, 0.0) + problem.weight
            for name, count in score.artifact.root.op_counts().items():
                family_key = "ref" if name == "ref" else "const" if name == "const" else name
                if family_key in family_counts:
                    family_counts[family_key] += count
            for statement in score.artifact.statements:
                for name, count in statement.expr.op_counts().items():
                    family_key = "ref" if name == "ref" else "const" if name == "const" else name
                    if family_key in family_counts:
                        family_counts[family_key] += count

        for category in sorted(category_totals):
            diagnostics[f"{category}_holdout_pass_rate"] = (
                category_totals[category] / category_weights[category]
            )
            behavior.append(diagnostics[f"{category}_holdout_pass_rate"])

        normalizer = max(sum(family_counts.values()), 1)
        behavior.extend(family_counts[name] / normalizer for name in family_names)
        return TaskEvaluation(
            objective_score=objective,
            behavior=tuple(behavior),
            diagnostics=diagnostics,
        )

    def render_candidate_report(self, network: NeuralNetwork) -> str:
        lines: list[str] = []
        for index, problem in enumerate(self.problems):
            artifact = self._build_artifact(network, problem, index)
            score = self._evaluate_artifact(artifact)
            lines.append(f"# {problem.name}")
            lines.append(
                f"{problem.prompt} [{problem.category}, difficulty={problem.difficulty:.2f}]"
            )
            lines.append(artifact.source_code.rstrip())
            lines.append(
                "train="
                f"{score.train_pass_rate:.2f} holdout={score.holdout_pass_rate:.2f} "
                f"nodes={artifact.node_count} lines={artifact.line_count}"
            )
            lines.append("")
        return "\n".join(lines).rstrip()


_ADVANCED_PROBLEMS = (
    CodeProblem(
        name="sum_two",
        prompt="Return the sum of two numbers.",
        arg_names=("a", "b"),
        output_kind="num",
        train_cases=(CodeCase((1, 2), 3), CodeCase((-2, 5), 3), CodeCase((0, 0), 0)),
        holdout_cases=(CodeCase((9, -4), 5), CodeCase((-7, -3), -10), CodeCase((10, 10), 20)),
        tags={"add": 1.0},
        category="arithmetic",
        difficulty=0.92,
        weight=0.9,
    ),
    CodeProblem(
        name="max_two",
        prompt="Return the larger of two numbers.",
        arg_names=("a", "b"),
        output_kind="num",
        train_cases=(CodeCase((1, 5), 5), CodeCase((8, 3), 8), CodeCase((-2, -7), -2)),
        holdout_cases=(CodeCase((0, 0), 0), CodeCase((-1, 4), 4), CodeCase((12, 6), 12)),
        tags={"max": 1.0, "gt": 0.8, "condition": 0.4},
        category="branching",
        difficulty=0.97,
        weight=1.0,
    ),
    CodeProblem(
        name="abs_diff",
        prompt="Return the absolute difference between two numbers.",
        arg_names=("a", "b"),
        output_kind="num",
        train_cases=(CodeCase((5, 2), 3), CodeCase((2, 5), 3), CodeCase((-3, 4), 7)),
        holdout_cases=(CodeCase((10, 10), 0), CodeCase((-7, -2), 5), CodeCase((6, -8), 14)),
        tags={"sub": 1.0, "abs": 1.0},
        category="arithmetic",
        difficulty=1.02,
        weight=1.05,
    ),
    CodeProblem(
        name="is_even",
        prompt="Return True when the number is even.",
        arg_names=("n",),
        output_kind="bool",
        train_cases=(CodeCase((0,), True), CodeCase((1,), False), CodeCase((4,), True), CodeCase((7,), False)),
        holdout_cases=(CodeCase((10,), True), CodeCase((-3,), False), CodeCase((12,), True)),
        tags={"mod": 1.0, "eq": 1.0},
        category="boolean",
        difficulty=1.0,
        weight=1.0,
    ),
    CodeProblem(
        name="clamp_unit",
        prompt="Clamp a number into the inclusive range from 0 to 1.",
        arg_names=("x",),
        output_kind="num",
        train_cases=(CodeCase((-0.4,), 0.0), CodeCase((0.25,), 0.25), CodeCase((1.8,), 1.0)),
        holdout_cases=(CodeCase((0.0,), 0.0), CodeCase((1.0,), 1.0), CodeCase((0.75,), 0.75), CodeCase((-2.2,), 0.0)),
        tags={"max": 1.0, "min": 1.0, "clamp": 1.0, "condition": 0.2},
        category="branching",
        difficulty=1.03,
        weight=1.1,
    ),
    CodeProblem(
        name="select_positive",
        prompt="Return the first number when it is positive, otherwise return the second number.",
        arg_names=("primary", "fallback"),
        output_kind="num",
        train_cases=(CodeCase((3, 9), 3), CodeCase((-1, 9), 9), CodeCase((0, 5), 5)),
        holdout_cases=(CodeCase((8, -2), 8), CodeCase((-7, -2), -2), CodeCase((1, 1), 1)),
        tags={"gt": 1.0, "condition": 1.0},
        category="branching",
        difficulty=1.01,
        weight=1.05,
    ),
    CodeProblem(
        name="median_three",
        prompt="Return the median of three numbers.",
        arg_names=("a", "b", "c"),
        output_kind="num",
        train_cases=(CodeCase((1, 5, 3), 3), CodeCase((9, 2, 7), 7), CodeCase((-1, -5, 4), -1)),
        holdout_cases=(CodeCase((0, 0, 9), 0), CodeCase((12, 8, 10), 10), CodeCase((-3, -7, -5), -5)),
        tags={"max": 1.0, "min": 1.0, "median": 1.0, "reuse": 0.8},
        category="composition",
        difficulty=1.15,
        weight=1.2,
    ),
    CodeProblem(
        name="between_inclusive",
        prompt="Return True when x is between low and high, inclusive.",
        arg_names=("x", "low", "high"),
        output_kind="bool",
        train_cases=(CodeCase((4, 2, 6), True), CodeCase((1, 2, 6), False), CodeCase((6, 2, 6), True)),
        holdout_cases=(CodeCase((2, 2, 6), True), CodeCase((8, 2, 6), False), CodeCase((5, 5, 5), True)),
        tags={"gt": 1.0, "lt": 1.0, "logic": 1.0, "between": 1.0},
        category="boolean",
        difficulty=1.08,
        weight=1.1,
    ),
    CodeProblem(
        name="distance_to_span",
        prompt="Return 0 when x is inside [low, high], otherwise return the distance to the nearest boundary.",
        arg_names=("x", "low", "high"),
        output_kind="num",
        train_cases=(CodeCase((4, 2, 6), 0), CodeCase((1, 2, 6), 1), CodeCase((8, 2, 6), 2)),
        holdout_cases=(CodeCase((2, 2, 6), 0), CodeCase((-3, -1, 4), 2), CodeCase((10, 2, 6), 4)),
        tags={"sub": 1.0, "gt": 0.6, "lt": 0.6, "condition": 1.0, "between": 0.5},
        category="composition",
        difficulty=1.18,
        weight=1.25,
    ),
    CodeProblem(
        name="closer_to_zero",
        prompt="Return whichever number is closer to zero. When tied, return the first number.",
        arg_names=("a", "b"),
        output_kind="num",
        train_cases=(CodeCase((5, -2), -2), CodeCase((-1, 4), -1), CodeCase((3, -3), 3)),
        holdout_cases=(CodeCase((7, -6), -6), CodeCase((-2, 2), -2), CodeCase((0.5, -0.75), 0.5)),
        tags={"abs": 1.0, "lt": 0.7, "condition": 1.0, "reuse": 0.7},
        category="composition",
        difficulty=1.14,
        weight=1.2,
    ),
    CodeProblem(
        name="sign_label",
        prompt="Return -1 for negative numbers, 1 for positive numbers, and 0 for zero.",
        arg_names=("x",),
        output_kind="num",
        train_cases=(CodeCase((-4,), -1), CodeCase((0,), 0), CodeCase((9,), 1)),
        holdout_cases=(CodeCase((-1,), -1), CodeCase((7,), 1), CodeCase((0.0,), 0)),
        tags={"gt": 0.8, "lt": 0.8, "condition": 1.0},
        category="branching",
        difficulty=1.1,
        weight=1.15,
    ),
)
