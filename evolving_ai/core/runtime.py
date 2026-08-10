from __future__ import annotations

from typing import Any, Callable, List
from .engine import EvolutionEngine, EvolutionConfig, GenerationSummary
from .archive import NoveltyArchive
from .task import Task


class EvolutionRuntime:
    def __init__(self, engine: EvolutionEngine) -> None:
        self.engine = engine

    @classmethod
    def from_task(
        cls,
        task: Task,
        initial_population: List[Any],
        config: EvolutionConfig | None = None,
    ) -> "EvolutionRuntime":
        cfg = config or EvolutionConfig()
        archive = NoveltyArchive()
        engine = EvolutionEngine(cfg, task, archive)
        return cls(engine)

    def run(
        self,
        initial_population: List[Any],
        progress_callback: Callable[[GenerationSummary], None] | None = None,
    ) -> Any:
        return self.engine.run(initial_population, progress_callback=progress_callback)