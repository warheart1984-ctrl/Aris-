"""Governed substrate verbs for UL stdlib v0.1."""

from __future__ import annotations

from typing import Dict

from ul_stdlib import call_stdlib


def patch_verb_capabilities() -> Dict[str, str]:
    from ul_substrate import Capability

    return {
        "prepares": Capability.MUTATE,
        "organizes": Capability.MUTATE,
        "remembers": Capability.MUTATE,
        "recalls": Capability.QUERY,
        "notices": Capability.HARMLESS,
        "summarizes": Capability.HARMLESS,
    }


def apply_stdlib_verbs_to_substrate() -> None:
    import ul_substrate as us

    for verb, cap in patch_verb_capabilities().items():
        us.VERB_CAPABILITIES[verb] = cap


def register_stdlib_handlers(runtime) -> None:
    def _workspace(actor, verb, times, context):
        name = context.get("workspace_name") or actor.replace("_", " ").title()
        return call_stdlib("auto.workspace", [name], context)

    def _organize(actor, verb, times, context):
        source = context.get("organize_source") or context.get("source") or "."
        return call_stdlib("auto.organize_plan", [source], context)

    def _remember(actor, verb, times, context):
        key = context.get("memory_key") or actor
        value = context.get("memory_value") or f"{actor}.{verb} x{times}"
        workspace = context.get("workspace_id") or ""
        return call_stdlib("state.remember", [key, value, workspace], context)

    def _recall(actor, verb, times, context):
        key = context.get("memory_key") or actor
        workspace = context.get("workspace_id") or ""
        return call_stdlib("state.recall", [key, workspace], context)

    def _report(actor, verb, times, context):
        if actor in {"device", "storage", "net", "system"}:
            return call_stdlib("device.status", [], context)
        return call_stdlib("auto.status", [], context)

    def _notice(actor, verb, times, context):
        text = context.get("notice") or f"{actor}.{verb} x{times}"
        return call_stdlib("ui.notice", [text], context)

    def _summary(actor, verb, times, context):
        text = context.get("summary_text") or context.get("prompt") or actor
        return call_stdlib("agent.summary", [text], context)

    runtime.dispatcher.register("prepares", _workspace)
    runtime.dispatcher.register("organizes", _organize)
    runtime.dispatcher.register("remembers", _remember)
    runtime.dispatcher.register("recalls", _recall)
    runtime.dispatcher.register("reports", _report)
    runtime.dispatcher.register("notices", _notice)
    runtime.dispatcher.register("summarizes", _summary)

