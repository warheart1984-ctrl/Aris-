from __future__ import annotations

from .genome import Genome, DenseGenome
from .task import Task, XorTask, SequencePredictionTask, create_task
from .archive import ArchiveEntry, NoveltyArchive, MapElitesArchive, Archive
from .engine import EvolutionEngine, EvolutionConfig, EvaluatedCandidate, GenerationSummary
from .runtime import EvolutionRuntime
from .config import ConfigBase, EvolutionConfig as CoreEvolutionConfig, TaskConfig, ArchiveConfig, ExperimentConfig
# Import NetworkShape and MutationConfig from legacy modules
from ..config import NetworkShape
from ..genomes import MutationConfig
from ..engines import (
    CEPEvolutionEngine,
    IntentPattern,
    ConstitutionalGenome,
    EvidenceRecord,
    LineageRecord,
    ConstitutionalCandidate,
    CEPGenerationSummary,
    PromotionTier,
    MutationOperatorType,
    RMLCMetaLearner,
    CEPForgeEvaluator,
    ConstitutionalSelection,
)
from .plugins import (
    PluginRegistry,
    task_registry,
    archive_registry,
    engine_registry,
    genome_registry,
    register_task,
    register_archive,
    register_engine,
    register_genome,
)

__all__ = [
    "Genome",
    "DenseGenome",
    "Task",
    "XorTask",
    "SequencePredictionTask",
    "create_task",
    "ArchiveEntry",
    "NoveltyArchive",
    "MapElitesArchive",
    "Archive",
    "EvolutionEngine",
    "EvolutionConfig",
    "EvaluatedCandidate",
    "GenerationSummary",
    "EvolutionRuntime",
    "ConfigBase",
    "CoreEvolutionConfig",
    "TaskConfig",
    "ArchiveConfig",
    "ExperimentConfig",
    "NetworkShape",
    "MutationConfig",
    "PluginRegistry",
    "task_registry",
    "archive_registry",
    "engine_registry",
    "genome_registry",
    "register_task",
    "register_archive",
    "register_engine",
    "register_genome",
    "CEPEvolutionEngine",
    "IntentPattern",
    "ConstitutionalGenome",
    "EvidenceRecord",
    "LineageRecord",
    "ConstitutionalCandidate",
    "CEPGenerationSummary",
    "PromotionTier",
    "MutationOperatorType",
    "RMLCMetaLearner",
    "CEPForgeEvaluator",
    "ConstitutionalSelection",
]