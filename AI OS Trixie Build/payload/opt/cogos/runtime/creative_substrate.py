"""
creative_substrate.py — Register creative UL verbs on SubstrateRuntime.
"""

from __future__ import annotations

from typing import Any, Dict

from creative_modules import run_creative


def register_creative_handlers(runtime) -> None:
    """Attach Story Forge / Beatbox / World3D handlers to a SubstrateRuntime."""

    def _story_draft(actor, verb, times, context):
        prompt = context.get("prompt", f"{actor} creative request")
        r = run_creative("story_forge", verb, prompt=prompt, context=context)
        return r.summary if r.ok else f"BLOCKED: {r.summary}"

    def _story_render(actor, verb, times, context):
        r = run_creative("story_forge", verb, context=context)
        return r.summary

    def _beatbox_score(actor, verb, times, context):
        r = run_creative("beatbox", verb, context=context)
        return r.summary

    def _beatbox_mix(actor, verb, times, context):
        r = run_creative("beatbox", verb, context=context)
        return r.summary

    def _world_build(actor, verb, times, context):
        prompt = context.get("prompt", "world")
        r = run_creative("world3d", verb, prompt=prompt, context=context)
        return r.summary

    runtime.dispatcher.register("drafts", _story_draft)
    runtime.dispatcher.register("renders", _story_render)
    runtime.dispatcher.register("scores", _beatbox_score)
    runtime.dispatcher.register("mixes", _beatbox_mix)
    runtime.dispatcher.register("builds", _world_build)


def patch_verb_capabilities() -> Dict[str, str]:
    """Verbs to merge into VERB_CAPABILITIES when bootstrapping."""
    from ul_substrate import Capability

    return {
        "drafts": Capability.MUTATE,
        "renders": Capability.MUTATE,
        "composes": Capability.MUTATE,
        "scores": Capability.MUTATE,
        "mixes": Capability.MUTATE,
        "plays": Capability.HARMLESS,
        "builds": Capability.MUTATE,
    }


def apply_creative_verbs_to_substrate() -> None:
    import ul_substrate as us

    for verb, cap in patch_verb_capabilities().items():
        us.VERB_CAPABILITIES[verb] = cap
