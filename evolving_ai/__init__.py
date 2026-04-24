"""Evolving AI package."""

from .archive import NoveltyArchive
from .code_agents import CodeWritingBenchmarkTask
from .config import EvolutionConfig, NetworkShape
from .engine import EvolutionEngine, EvolutionResult, GenerationSummary
from .genome import Genome
from .tasks import SequencePredictionTask, TaskEvaluation, XorTask

__all__ = [
    "EvolutionConfig",
    "EvolutionEngine",
    "EvolutionResult",
    "GenerationSummary",
    "Genome",
    "NetworkShape",
    "NoveltyArchive",
    "CodeWritingBenchmarkTask",
    "SequencePredictionTask",
    "TaskEvaluation",
    "XorTask",
]
