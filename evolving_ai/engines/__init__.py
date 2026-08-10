from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any, Callable, Generic, Protocol, TypeVar
import numpy as np

from ..config import ConfigBase
from ..core import Genome, NetworkShape, MutationConfig, Task, Archive
from ..core.genome import DenseGenome

GenomeT = TypeVar("GenomeT", bound=Genome)
PhenotypeT = TypeVar("PhenotypeT")


@dataclass(frozen=True, slots=True)
class EvaluatedCandidate(Generic[GenomeT]):
    genome: GenomeT
    objective_score: float
    novelty_score: float
    combined_score: float
    behavior: tuple[float, ...]
    diagnostics: dict[str, float]

    def to_dict(self) -> dict[str, Any]:
        return {
            "objective_score": self.objective_score,
            "novelty_score": self.novelty_score,
            "combined_score": self.combined_score,
            "behavior": list(self.behavior),
            "diagnostics": self.diagnostics,
            "genome": self.genome.to_dict(),
        }


@dataclass(frozen=True, slots=True)
class GenerationSummary:
    generation: int
    best_objective: float
    best_combined: float
    average_objective: float
    average_novelty: float
    archive_size: int
    stagnation: int

    def to_dict(self) -> dict[str, Any]:
        return {
            "generation": self.generation,
            "best_objective": self.best_objective,
            "best_combined": self.best_combined,
            "average_objective": self.average_objective,
            "average_novelty": self.average_novelty,
            "archive_size": self.archive_size,
            "stagnation": self.stagnation,
        }


@dataclass(frozen=True, slots=True)
class EvolutionResult(Generic[GenomeT]):
    task_name: str
    best: EvaluatedCandidate[GenomeT]
    hall_of_fame: tuple[EvaluatedCandidate[GenomeT], ...]
    history: tuple[GenerationSummary, ...]
    archive_size: int

    def to_dict(self) -> dict[str, Any]:
        return {
            "task_name": self.task_name,
            "best": self.best.to_dict(),
            "hall_of_fame": [c.to_dict() for c in self.hall_of_fame],
            "history": [h.to_dict() for h in self.history],
            "archive_size": self.archive_size,
        }


class EvolutionEngine(ABC, Generic[GenomeT, PhenotypeT]):
    @abstractmethod
    def run(
        self,
        progress_callback: Callable[[GenerationSummary], None] | None = None,
    ) -> EvolutionResult[GenomeT]:
        pass

    @abstractmethod
    def save_result(self, path: str, result: EvolutionResult[GenomeT]) -> None:
        pass


@dataclass(frozen=True, slots=True)
class EvolutionConfig(ConfigBase):
    CONFIG_TYPE = "evolution_config"
    population_size: int = 96
    generations: int = 80
    elite_fraction: float = 0.1
    crossover_rate: float = 0.7
    mutation_probability: float = 0.18
    mutation_strength: float = 0.35
    mutation_scale_learning_rate: float = 0.12
    tournament_size: int = 5
    novelty_weight: float = 0.25
    archive_probability: float = 0.2
    behavior_neighbors: int = 5
    stagnation_limit: int = 10
    diversity_injection_fraction: float = 0.15
    hall_of_fame_size: int = 5
    seed: int | None = None

    @property
    def elite_count(self) -> int:
        return max(1, int(self.population_size * self.elite_fraction))

    @property
    def diversity_injection_count(self) -> int:
        return int(self.population_size * self.diversity_injection_fraction)

    def to_mutation_config(self) -> MutationConfig:
        return MutationConfig(
            mutation_probability=self.mutation_probability,
            mutation_strength=self.mutation_strength,
            mutation_scale_learning_rate=self.mutation_scale_learning_rate,
        )


class SelectionStrategy(Protocol):
    def __call__(
        self,
        population: list[EvaluatedCandidate],
        tournament_size: int,
        rng: np.random.Generator,
    ) -> EvaluatedCandidate:
        ...


# Re-export CEP engine components
from .cep import (
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

# Re-export CEP integration components
from .cep_integration import (
    CEPArisIntegration,
    CEPArisIntegrationConfig,
)

# Re-export CEP CIEMS integration
from .cep_ciems import (
    CIEMSForgeEvaluator,
    CEPForgeEvaluatorAdapter,
    CIEMSEvaluationConfig,
    create_ciems_evaluator,
)

# Re-export CEP SovereignX integration
from .cep_sovereignx import (
    SovereignXRenderer,
    SovereignXRenderConfig,
    SMEFrame,
    SMERenderResult,
    FLUXIngestResult,
    SMEFrameCallback,
    create_sovereignx_renderer,
)

# Re-export CEP Orchestration
from .cep_orchestration import (
    CEPOrchestrationService,
    CEPOrchestrationConfig,
    CEPRunResult,
    create_cep_orchestration,
)

__all__ = [
    "EvaluatedCandidate",
    "GenerationSummary",
    "EvolutionResult",
    "EvolutionEngine",
    "EvolutionConfig",
    "SelectionStrategy",
    "tournament_selection",
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
    "CEPArisIntegration",
    "CEPArisIntegrationConfig",
    "CIEMSForgeEvaluator",
    "CEPForgeEvaluatorAdapter",
    "CIEMSEvaluationConfig",
    "create_ciems_evaluator",
    "SovereignXRenderer",
    "SovereignXRenderConfig",
    "SMEFrame",
    "SMERenderResult",
    "FLUXIngestResult",
    "SMEFrameCallback",
    "create_sovereignx_renderer",
    "CEPOrchestrationService",
    "CEPOrchestrationConfig",
    "CEPRunResult",
    "create_cep_orchestration",
]


def tournament_selection(
    population: list[EvaluatedCandidate],
    tournament_size: int,
    rng: np.random.Generator,
) -> EvaluatedCandidate:
    competitors = rng.choice(population, size=min(tournament_size, len(population)), replace=False)
    return max(competitors, key=lambda c: (c.combined_score, c.objective_score))