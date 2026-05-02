from __future__ import annotations

import re
from typing import Any, Mapping


BRAIN_MODE_OPTIONS = (
    "Chat",
    "Inspect",
    "Plan",
    "Build",
    "Evaluate",
    "Route",
    "Memory",
    "Approval",
)

BRAIN_SCOPE_OPTIONS = (
    "Current Chat",
    "Selected Repo",
    "Selected Task",
    "Workspace",
    "Runtime",
    "Memory Bank",
    "All Context",
)

BRAIN_TARGET_OPTIONS = (
    "ARIS Only",
    "Forge",
    "ForgeEval",
    "Runtime",
    "Memory",
    "Operator Review",
)

BRAIN_PERMISSION_OPTIONS = (
    "Read Only",
    "Suggest Only",
    "Approval Required",
    "Execute Safe Actions",
    "Governed Workspace Mode",
)

BRAIN_RESPONSE_STYLE_OPTIONS = (
    "Direct",
    "Operator",
    "Technical",
    "Strategic",
    "Concise",
    "Guided",
)

DEFAULT_BRAIN_STATE = {
    "mode": "Inspect",
    "scope": "Selected Repo",
    "target": "ARIS Only",
    "permission": "Read Only",
    "response_style": "Technical",
}

PROTECTED_PATTERNS = (
    re.compile(r"\bevolving core\b", re.IGNORECASE),
    re.compile(r"\bevolving engine\b", re.IGNORECASE),
    re.compile(r"\bevolve the core\b", re.IGNORECASE),
    re.compile(r"\bmutate the core\b", re.IGNORECASE),
    re.compile(r"\bself[- ]?modify\b", re.IGNORECASE),
    re.compile(r"\bself[- ]?rewrite\b", re.IGNORECASE),
    re.compile(r"\badaptive core\b", re.IGNORECASE),
)


def seed_workspace_messages() -> list[dict[str, Any]]:
    return [
        {
            "role": "assistant",
            "content": (
                "ARIS workspace is online. I can inspect repos, plan tasks, route work to Forge, "
                "send evaluations to ForgeEval, and keep approval flow visible without surfacing "
                "protected core paths."
            ),
            "created_at": "",
        },
        {
            "role": "user",
            "content": "Inspect the selected repo, then prep the approval path for the task board.",
            "created_at": "",
        },
        {
            "role": "assistant",
            "content": (
                "Repo inspection ready. I found two likely routing seams and one approval-sensitive "
                "path in the selected codebase. I can hold the task-board route for approval or send "
                "a worker packet to Forge next."
            ),
            "created_at": "",
        },
    ]


def _brain_value(brain_state: Mapping[str, Any], key: str) -> str:
    fallback = str(DEFAULT_BRAIN_STATE.get(key, "")).strip()
    value = str(brain_state.get(key, fallback) or fallback).strip()
    return value or fallback


def current_brain_state(brain_state: Mapping[str, Any] | None = None) -> dict[str, str]:
    payload = dict(brain_state or {})
    return {
        "mode": _brain_value(payload, "mode"),
        "scope": _brain_value(payload, "scope"),
        "target": _brain_value(payload, "target"),
        "permission": _brain_value(payload, "permission"),
        "response_style": _brain_value(payload, "response_style"),
    }


def protected_request(prompt: str, target: str) -> bool:
    text = f"{prompt or ''} {target or ''}"
    return any(pattern.search(text) for pattern in PROTECTED_PATTERNS)


def route_for_target(target: str) -> list[str]:
    normalized = str(target or "").strip()
    if normalized == "Forge":
        return ["Jarvis Blueprint", "Operator", "Forge", "Outcome"]
    if normalized == "ForgeEval":
        return ["Jarvis Blueprint", "Operator", "ForgeEval", "Outcome"]
    if normalized == "Runtime":
        return ["Jarvis Blueprint", "Operator", "Runtime", "Outcome"]
    if normalized == "Memory":
        return ["Jarvis Blueprint", "Operator", "Memory", "Outcome"]
    return ["Jarvis Blueprint", "Operator", "Governance Review", "Outcome"]


def workspace_status_pills(brain_state: Mapping[str, Any]) -> list[str]:
    brain = current_brain_state(brain_state)
    approval_pill = (
        "Approval Gated"
        if brain["permission"] in {"Approval Required", "Suggest Only", "Read Only"}
        else "Governed Workspace Actions"
    )
    return ["Forge Available", approval_pill, "Evolving Core Locked"]


def _scope_label(brain: Mapping[str, str], repo: Mapping[str, Any] | None, task: Mapping[str, Any] | None) -> str:
    scope = str(brain.get("scope", "")).strip()
    if scope == "Selected Repo":
        return str(repo.get("name", "the selected repo")) if isinstance(repo, Mapping) else "the selected repo"
    if scope == "Selected Task":
        if isinstance(task, Mapping):
            return f"{task.get('id', 'task')} {task.get('title', 'selected task')}".strip()
        return "the selected task"
    if scope == "Current Chat":
        return "the current chat"
    if scope == "Workspace":
        return "the workspace"
    if scope == "Runtime":
        return "runtime state"
    if scope == "Memory Bank":
        return "the memory bank"
    return "all active context"


def _target_clause(brain: Mapping[str, str]) -> str:
    target = str(brain.get("target", "")).strip()
    if target == "ARIS Only":
        return "I will keep this inside ARIS and the workspace surface."
    if target == "Forge":
        return "Forge is the worker lane, but ARIS remains the speaker and narrator."
    if target == "ForgeEval":
        return "ForgeEval is the review lane, so I will frame this as evaluation instead of direct execution."
    if target == "Runtime":
        return "I will keep this in runtime inspection and workspace actions."
    if target == "Memory":
        return "I will keep this in memory shaping and context anchoring."
    return "I will package the next step for operator review instead of direct worker execution."


def _permission_clause(permission: str) -> str:
    normalized = str(permission or "").strip()
    if normalized == "Read Only":
        return "Nothing will execute from this route."
    if normalized == "Suggest Only":
        return "I will stop at suggestions, notes, and next actions."
    if normalized == "Approval Required":
        return "I will hold the route pending approval."
    if normalized == "Execute Safe Actions":
        return "I can simulate safe governed workspace actions on the selected task."
    return "I can widen governed workspace actions, but protected routes remain closed."


def _suggestions_for_decision(brain: Mapping[str, str]) -> list[str]:
    target = str(brain.get("target", "")).strip()
    mode = str(brain.get("mode", "")).strip()
    if target == "Forge":
        return ["Approve Forge Route", "Inspect Diff Packet", "Shift To ForgeEval"]
    if target == "ForgeEval":
        return ["Review Findings", "Route To Forge", "Hold For Operator Review"]
    if target == "Operator Review":
        return ["Open Approval Packet", "Inspect Repo", "Plan Next Task"]
    if mode == "Memory":
        return ["Store Repo Context", "Link Selected Task", "Return To Planning"]
    return ["Inspect Selected Repo", "Plan Selected Task", "Route To Forge"]


def _style_wrap(base: str, brain: Mapping[str, str], suggestions: list[str]) -> str:
    style = str(brain.get("response_style", "")).strip()
    safe_suggestions = ", ".join(suggestions[:3]).lower()
    if style == "Direct":
        return base
    if style == "Operator":
        return f"{base} I am keeping the operator surface stable and the handoff explicit."
    if style == "Technical":
        scope = str(brain.get("scope", "the workspace")).lower()
        return f"{base} The route stays observable, approval-aware, and bounded to {scope}."
    if style == "Strategic":
        return f"{base} This keeps momentum without widening authority or losing operator visibility."
    if style == "Concise":
        return f"{base.split('. ')[0]}."
    if style == "Guided":
        return f"{base} I can continue with {safe_suggestions}, next."
    return base


def build_workspace_decision(
    *,
    prompt: str,
    brain_state: Mapping[str, Any],
    repo: Mapping[str, Any] | None,
    task: Mapping[str, Any] | None,
) -> dict[str, Any]:
    brain = current_brain_state(brain_state)
    repo_name = str(repo.get("name", "the selected repo")) if isinstance(repo, Mapping) else "the selected repo"
    task_name = str(task.get("title", "the selected task")) if isinstance(task, Mapping) else "the selected task"
    scoped_to = _scope_label(brain, repo, task)

    if protected_request(prompt, brain["target"]):
        return {
            "blocked": True,
            "content": (
                "That path is protected and unavailable from this workspace. "
                "The evolving core is not exposed to ARIS in this workspace. "
                "I can continue through Forge, evaluation, approval flow, or standard workspace actions instead."
            ),
            "summary": "Protected route blocked",
            "route": route_for_target("ARIS Only"),
            "suggestions": [
                "Route To Forge",
                "Send To ForgeEval",
                "Hold For Approval",
                "Inspect In Read Only",
                "Plan Next Task",
            ],
            "pills": ["Protected Boundary", "Forge Available", "Evolving Core Locked"],
            "tone": "warning",
            "worker_title": "Protected Boundary",
            "worker_status": "Locked",
            "worker_lines": [
                "ARIS refused the protected request before any route could open.",
                "The evolving core is not available from this workspace.",
                "Forge, ForgeEval, approvals, and read-only workspace actions remain available.",
            ],
            "task_status": "Review" if isinstance(task, Mapping) else None,
            "task_update": (
                "Protected route blocked. ARIS offered Forge, ForgeEval, approval flow, and read-only alternatives."
                if isinstance(task, Mapping)
                else None
            ),
            "activity_title": "Protected route blocked",
            "activity_detail": "ARIS held the workspace boundary and redirected the operator toward allowed paths.",
        }

    example_key = "|".join(
        [brain["mode"], brain["scope"], brain["target"], brain["permission"], brain["response_style"]]
    )
    if example_key == "Inspect|Selected Repo|ARIS Only|Read Only|Technical":
        base_content = f"Repo inspection ready. I found two likely routing seams and one approval-sensitive path in {repo_name}."
        summary = "Repo seams surfaced"
    elif example_key == "Build|Selected Task|Forge|Approval Required|Operator":
        base_content = "This task is ready to route to Forge. I have prepared the execution path and held it pending approval."
        summary = "Forge route prepared"
    elif example_key == "Evaluate|Workspace|ForgeEval|Suggest Only|Strategic":
        base_content = "I reviewed the workspace flow and found one weak handoff between planning and execution."
        summary = "Evaluation packet prepared"
    else:
        mode = brain["mode"]
        if mode == "Chat":
            base_content = f"I am holding the operator conversation on {scoped_to}. {_target_clause(brain)} {_permission_clause(brain['permission'])}"
            summary = "Operator conversation framed"
        elif mode == "Inspect":
            base_content = (
                f"Inspection frame is active for {scoped_to}. I found the main routing, approval, and handoff signals "
                f"around {repo_name}. {_permission_clause(brain['permission'])}"
            )
            summary = "Inspection lane active"
        elif mode == "Plan":
            base_content = (
                f"Planning frame is active for {scoped_to}. I turned {task_name} into a staged path with a visible "
                f"approval checkpoint. {_target_clause(brain)}"
            )
            summary = "Plan staged"
        elif mode == "Build":
            if brain["target"] == "Forge":
                base_content = (
                    f"I can route {task_name} to Forge from this workspace. The worker lane stays behind ARIS, "
                    f"and {_permission_clause(brain['permission']).lower()}"
                )
            else:
                base_content = (
                    f"Build framing is active for {task_name}. I can shape the implementation path here first, "
                    "then hand it to the selected target when you are ready."
                )
            summary = "Build path prepared"
        elif mode == "Evaluate":
            if brain["target"] == "ForgeEval":
                base_content = (
                    f"ForgeEval is available for {scoped_to}. I can send the packet there and keep the result "
                    "narrated through ARIS."
                )
            else:
                base_content = (
                    f"Evaluation frame is active for {scoped_to}. I can review seams, approvals, and worker "
                    "handoffs before anything applies."
                )
            summary = "Evaluation lane active"
        elif mode == "Route":
            base_content = (
                f"Routing frame is ready. I can hand {task_name} to {brain['target']} while keeping ARIS as the "
                f"speaking face and {_permission_clause(brain['permission']).lower()}"
            )
            summary = "Route mapped"
        elif mode == "Memory":
            base_content = (
                f"Memory framing is active for {scoped_to}. I can anchor repo, task, and operator context without "
                f"widening execution scope. {_target_clause(brain)}"
            )
            summary = "Memory context prepared"
        elif mode == "Approval":
            base_content = (
                f"Approval framing is active for {task_name}. I summarized the next action, the risk posture, "
                "and the exact gate you would open from this workspace."
            )
            summary = "Approval packet ready"
        else:
            base_content = (
                f"I can operate on {scoped_to} from ARIS and keep the workspace readable while the selected route "
                "stays visible."
            )
            summary = "Workspace route prepared"

    suggestions = _suggestions_for_decision(brain)
    content = _style_wrap(base_content, brain, suggestions)
    task_status = str(task.get("status", "")).strip() if isinstance(task, Mapping) else None
    task_update = str(task.get("latest_update", "")).strip() if isinstance(task, Mapping) else None
    worker_title = "ARIS Control Lane"
    worker_status = "Review" if brain["permission"] == "Approval Required" else "Ready"
    worker_lines = [f"Mode: {brain['mode']}", f"Scope: {brain['scope']}", f"Target: {brain['target']}"]

    if brain["target"] == "Forge":
        worker_title = "Forge Route"
        if brain["permission"] in {"Approval Required", "Suggest Only", "Read Only"}:
            worker_status = "Review"
            task_status = "Review" if isinstance(task, Mapping) else None
            task_update = "ARIS prepared the Forge route and held apply behind approval." if isinstance(task, Mapping) else None
            worker_lines = [
                "Forge is available as the worker lane.",
                "ARIS prepared the route and kept apply pending approval.",
                "Evolving core remains locked and unavailable.",
            ]
        else:
            worker_status = "Running"
            task_status = "Running" if isinstance(task, Mapping) else None
            task_update = "Forge is preparing the task now under the selected workspace controls." if isinstance(task, Mapping) else None
            worker_lines = [
                "Forge is preparing the task now.",
                "ARIS is narrating the worker lane and keeping the route visible.",
                "Approval and locked-boundary signals remain on screen.",
            ]
    elif brain["target"] == "ForgeEval":
        worker_title = "ForgeEval Review"
        worker_status = "Review"
        task_status = "Review" if isinstance(task, Mapping) else None
        task_update = "ForgeEval is reviewing the route and highlighting the weak handoff." if isinstance(task, Mapping) else None
        worker_lines = [
            "ForgeEval is reviewing the selected route.",
            "ARIS will narrate the findings and next safe move.",
            "No protected route is exposed during evaluation.",
        ]
    elif brain["target"] == "Operator Review":
        worker_title = "Approval Packet"
        worker_status = "Review"
        task_status = "Review" if isinstance(task, Mapping) else None
        task_update = "ARIS packaged the task for operator review and kept execution closed." if isinstance(task, Mapping) else None
        worker_lines = [
            "Operator review packet is assembled.",
            "ARIS is holding the approval gate closed until you confirm.",
            "Forge remains available if you want a worker route next.",
        ]
    elif brain["target"] == "Memory":
        worker_title = "Memory Context"
        worker_status = "Ready"
        worker_lines = [
            "Memory and context remain available inside ARIS.",
            "No worker route is required for this step.",
            "Protected routes remain invisible and closed.",
        ]
    else:
        worker_status = "Ready"
        worker_lines = [
            "ARIS is keeping this route inside the workspace shell.",
            "No worker handoff is required for the selected target.",
            "Protected routes remain locked and unavailable.",
        ]

    return {
        "blocked": False,
        "content": content,
        "summary": summary,
        "route": route_for_target(brain["target"]),
        "suggestions": suggestions,
        "pills": [brain["mode"], brain["scope"], brain["target"], brain["permission"], brain["response_style"]],
        "tone": worker_status.lower(),
        "worker_title": worker_title,
        "worker_status": worker_status,
        "worker_lines": worker_lines,
        "task_status": task_status,
        "task_update": task_update,
        "activity_title": f"{brain['mode']} route updated",
        "activity_detail": f"{brain['target']} is now framed for {scoped_to} with {brain['permission'].lower()} active.",
    }
