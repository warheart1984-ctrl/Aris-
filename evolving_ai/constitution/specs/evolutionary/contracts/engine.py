from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any, Callable, Generic, List, Optional, Protocol, Sequence, TypeVar
import copy
import numpy as np

from evolving_ai.core import (
    EvolutionEngine,
    EvolutionConfig,
    EvaluatedCandidate,
    GenerationSummary,
    Genome,
    Task,
    Archive,
)

GenomeT = TypeVar("GenomeT", bound=Genome)


def _make_tracing_engine(engine: EvolutionEngine[GenomeT], replay: "DeterministicReplay") -> EvolutionEngine[GenomeT]:
    """Create a tracing engine that copies all state from the original engine."""
    traced = copy.copy(engine)
    traced.__dict__ = copy.deepcopy(engine.__dict__)
    traced.__class__ = engine.__class__
    
    # Replace run method with tracing version
    def tracing_run(initial_population, progress_callback=None):
        population = initial_population
        best = None
        for gen in range(traced.config.generations):
            scored = traced._evaluate_population(population)
            best = max(scored, key=lambda s: s.score)
            next_population = traced._next_generation(scored)

            if progress_callback:
                avg_fit = sum(s.fitness for s in scored) / len(scored)
                avg_nov = sum(s.novelty for s in scored) / len(scored)
                summary = GenerationSummary(
                    generation=gen,
                    best_fitness=best.fitness,
                    best_score=best.score,
                    avg_fitness=avg_fit,
                    avg_novelty=avg_nov,
                    archive_size=len(traced.archive.entries) if hasattr(traced.archive, 'entries') else 0,
                )
                progress_callback(summary)
            else:
                summary = GenerationSummary(
                    generation=gen,
                    best_fitness=best.fitness,
                    best_score=best.score,
                    avg_fitness=sum(s.fitness for s in scored) / len(scored),
                    avg_novelty=sum(s.novelty for s in scored) / len(scored),
                    archive_size=len(traced.archive.entries) if hasattr(traced.archive, 'entries') else 0,
                )

            replay.record_generation(gen, population, scored, next_population, summary)
            population = next_population
        return best
    
    traced.run = tracing_run
    return traced


class EngineContract(Protocol[GenomeT]):
    """Constitutional contract for any EvolutionEngine implementation.

    Laws (must hold for all conforming engines):
    1. Determinism: Same seed + same initial population → identical trajectory
    2. Elitism: Best fitness never decreases across generations (total preorder)
    3. Population Invariance: Population size constant per generation
    4. Archive Monotonicity: Archive size never decreases
    5. Selection Pressure: E[offspring fitness] ≥ E[parent fitness] under selection distribution
    6. Semantic Equivalence: Distributed evaluation produces same evidence bundle as sequential
    """

    @abstractmethod
    def check_determinism(
        self,
        engine_factory: Callable[[], EvolutionEngine[GenomeT]],
        initial_population: List[GenomeT],
        config: EvolutionConfig,
        num_runs: int = 3,
    ) -> "ContractResult":
        """Law 1: Determinism."""
        ...

    @abstractmethod
    def check_elitism(
        self,
        engine: EvolutionEngine[GenomeT],
        initial_population: List[GenomeT],
    ) -> "ContractResult":
        """Law 2: Elitism (best fitness non-decreasing under total preorder)."""
        ...

    @abstractmethod
    def check_population_invariance(
        self,
        engine: EvolutionEngine[GenomeT],
        initial_population: List[GenomeT],
    ) -> "ContractResult":
        """Law 3: Population size constant."""
        ...

    @abstractmethod
    def check_archive_monotonicity(
        self,
        engine: EvolutionEngine[GenomeT],
        initial_population: List[GenomeT],
    ) -> "ContractResult":
        """Law 4: Archive size non-decreasing."""
        ...

    @abstractmethod
    def check_optimization_pressure(
        self,
        engine: EvolutionEngine[GenomeT],
        initial_population: List[GenomeT],
        num_samples: int = 1000,
    ) -> "ContractResult":
        """Law 5: Optimization Pressure - Tournament selection by declared pressure must select better than random."""
        ...

    @abstractmethod
    def check_semantic_equivalence(
        self,
        engine_factory: Callable[[], EvolutionEngine[GenomeT]],
        initial_population: List[GenomeT],
        config: EvolutionConfig,
        distributed_backend: str = "thread",
    ) -> "ContractResult":
        """Law 6: Distributed evaluation produces same evidence bundle as sequential."""
        ...


@dataclass(frozen=True, slots=True)
class ContractResult:
    law_name: str
    passed: bool
    details: dict
    counterexample: Optional[Any] = None
    evidence_ref: Optional[str] = None

    def to_dict(self) -> dict:
        return {
            "law": self.law_name,
            "passed": bool(self.passed),  # Ensure Python bool
            "details": _json_safe(self.details),
            "counterexample": str(self.counterexample) if self.counterexample else None,
            "evidence_ref": self.evidence_ref,
        }


def _json_safe(obj: Any) -> Any:
    """Convert numpy types and other non-JSON-serializable types to Python native types."""
    import numpy as np
    if isinstance(obj, (np.bool_, np.integer)):
        return bool(obj) if isinstance(obj, np.bool_) else int(obj)
    elif isinstance(obj, np.floating):
        return float(obj)
    elif isinstance(obj, np.ndarray):
        return obj.tolist()
    elif isinstance(obj, bool):
        return bool(obj)
    elif isinstance(obj, dict):
        return {k: _json_safe(v) for k, v in obj.items()}
    elif isinstance(obj, (list, tuple)):
        return [_json_safe(v) for v in obj]
    else:
        return obj


@dataclass
class EvidenceBundle:
    engine_type: str
    config: dict
    results: List[ContractResult]
    provenance: "ProvenanceTrace"
    timestamp: str

    def all_passed(self) -> bool:
        return all(r.passed for r in self.results)

    def failed_laws(self) -> List[str]:
        return [r.law_name for r in self.results if not r.passed]

    def to_dict(self) -> dict:
        return _json_safe({
            "engine_type": self.engine_type,
            "config": self.config,
            "results": [r.to_dict() for r in self.results],
            "provenance": self.provenance.to_dict(),
            "timestamp": self.timestamp,
            "all_passed": self.all_passed(),
            "failed_laws": self.failed_laws(),
        })


@dataclass
class ProvenanceTrace:
    run_id: str
    seed: int
    initial_population_hashes: List[str]
    generation_events: List[dict]
    final_population_hashes: List[str]
    archive_snapshots: List[dict]

    def to_dict(self) -> dict:
        return _json_safe({
            "run_id": self.run_id,
            "seed": self.seed,
            "initial_population_hashes": self.initial_population_hashes,
            "generation_events": self.generation_events,
            "final_population_hashes": self.final_population_hashes,
            "archive_snapshots": self.archive_snapshots,
        })


class DeterministicReplay:
    """Records full deterministic replay of an engine run."""

    def __init__(self, engine: EvolutionEngine, seed: int, initial_population: List[GenomeT]):
        self.engine = engine
        self.seed = seed
        self.initial_population = initial_population
        self.events: List[dict] = []

    def record_generation(
        self,
        generation: int,
        population: List[GenomeT],
        scored: List[EvaluatedCandidate[GenomeT]],
        next_population: List[GenomeT],
        summary: GenerationSummary,
    ) -> None:
        self.events.append({
            "generation": generation,
            "population_hashes": [self._hash_genome(g) for g in population],
            "scored": [
                {
                    "genome_hash": self._hash_genome(s.genome),
                    "fitness": s.fitness,
                    "novelty": s.novelty,
                    "score": s.score,
                }
                for s in scored
            ],
            "next_population_hashes": [self._hash_genome(g) for g in next_population],
            "summary": {
                "generation": summary.generation,
                "best_fitness": summary.best_fitness,
                "best_score": summary.best_score,
                "avg_fitness": summary.avg_fitness,
                "avg_novelty": summary.avg_novelty,
                "archive_size": summary.archive_size,
            },
        })

    def _hash_genome(self, genome: GenomeT) -> str:
        import hashlib
        import json
        if hasattr(genome, 'to_dict'):
            data = json.dumps(genome.to_dict(), sort_keys=True).encode()
        elif hasattr(genome, 'weights'):
            data = json.dumps(genome.weights, sort_keys=True).encode()
        else:
            data = json.dumps(str(genome), sort_keys=True).encode()
        return hashlib.sha256(data).hexdigest()[:16]

    def get_trace(self) -> ProvenanceTrace:
        return ProvenanceTrace(
            run_id=f"run_{self.seed}",
            seed=self.seed,
            initial_population_hashes=[self._hash_genome(g) for g in self.initial_population],
            generation_events=self.events,
            final_population_hashes=[self._hash_genome(g) for g in self.events[-1]["next_population_hashes"]] if self.events else [],
            archive_snapshots=[],  # Filled by engine
        )


class ConformanceSuite(Generic[GenomeT]):
    """Runs all EngineContract laws against an implementation."""

    def __init__(self, contract: EngineContract[GenomeT]) -> None:
        self.contract = contract

    def run(
        self,
        engine_factory: Callable[[], EvolutionEngine[GenomeT]],
        initial_population: List[GenomeT],
        config: EvolutionConfig,
        engine_type: str,
    ) -> EvidenceBundle:
        engine = engine_factory()
        results = []

        # Law 1: Determinism
        results.append(self.contract.check_determinism(engine_factory, initial_population, config))

        # Law 2: Elitism
        results.append(self.contract.check_elitism(engine, initial_population))

        # Law 3: Population Invariance
        results.append(self.contract.check_population_invariance(engine, initial_population))

        # Law 4: Archive Monotonicity
        results.append(self.contract.check_archive_monotonicity(engine, initial_population))

        # Law 5: Optimization Pressure
        results.append(self.contract.check_optimization_pressure(engine, initial_population))

        # Law 6: Semantic Equivalence (optional, requires distributed backend)
        try:
            results.append(self.contract.check_semantic_equivalence(engine_factory, initial_population, config))
        except Exception as e:
            results.append(ContractResult(
                law_name="semantic_equivalence",
                passed=False,
                details={"error": str(e)},
                counterexample="distributed backend not available",
            ))

        from datetime import datetime
        import uuid
        provenance = self._collect_provenance(engine, initial_population, config)

        return EvidenceBundle(
            engine_type=engine_type,
            config=config.to_dict() if hasattr(config, 'to_dict') else str(config),
            results=results,
            provenance=provenance,
            timestamp=datetime.utcnow().isoformat(),
        )

    def _collect_provenance(self, engine: EvolutionEngine[GenomeT], initial_population: List[GenomeT], config: EvolutionConfig) -> ProvenanceTrace:
        replay = DeterministicReplay(engine, config.seed or 0, initial_population)
        traced_engine = _make_tracing_engine(engine, replay)
        traced_engine.run(initial_population)
        return replay.get_trace()