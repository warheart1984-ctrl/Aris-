from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Callable, List, Optional, Tuple, TypeVar
import random
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
    NoveltyArchive,
)
from evolving_ai.core.genome import DenseGenome

from .engine import EngineContract, ContractResult, EvidenceBundle, ProvenanceTrace, DeterministicReplay, ConformanceSuite

GenomeT = TypeVar("GenomeT", bound=Genome)


def _make_tracing_engine(engine: EvolutionEngine[GenomeT], replay: DeterministicReplay) -> EvolutionEngine[GenomeT]:
    """Create a tracing engine that copies all state from the original engine."""
    traced = copy.copy(engine)
    # Deepcopy state but exclude unpicklable backend (Dask/Ray clients with thread locks)
    state = copy.deepcopy(engine.__dict__)
    state.pop('_backend', None)
    traced.__dict__ = state
    traced.__class__ = engine.__class__
    
    # Replace run method with tracing version
    original_run = traced.run
    
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


class StandardEngineContract(EngineContract[GenomeT]):
    """Reference implementation of EngineContract checkers."""

    def check_determinism(
        self,
        engine_factory: Callable[[], EvolutionEngine[GenomeT]],
        initial_population: List[GenomeT],
        config: EvolutionConfig,
        num_runs: int = 3,
    ) -> ContractResult:
        """Law 1: Same seed + same initial population → identical trajectory."""
        trajectories = []

        for _ in range(num_runs):
            engine = engine_factory()
            replay = DeterministicReplay(engine, config.seed or 0, initial_population)
            traced_engine = _make_tracing_engine(engine, replay)
            traced_engine.run(initial_population)
            trajectories.append(replay.get_trace())

        # Compare all trajectories
        first = trajectories[0]
        all_match = all(
            t.generation_events == first.generation_events and
            t.final_population_hashes == first.final_population_hashes
            for t in trajectories[1:]
        )

        if not all_match:
            # Find first divergence
            for i, t in enumerate(trajectories[1:], 1):
                for gen_idx, (e1, e2) in enumerate(zip(first.generation_events, t.generation_events)):
                    if e1 != e2:
                        return ContractResult(
                            law_name="determinism",
                            passed=False,
                            details={"divergence_generation": gen_idx, "run": i},
                            counterexample=f"Run {i} diverged at generation {gen_idx}",
                        )

        return ContractResult(
            law_name="determinism",
            passed=True,
            details={"runs_compared": num_runs, "generations": len(first.generation_events)},
        )

    def check_elitism(
        self,
        engine: EvolutionEngine[GenomeT],
        initial_population: List[GenomeT],
    ) -> ContractResult:
        """Law 2: Maximum fitness in population never decreases (total preorder - ties allowed)."""
        replay = DeterministicReplay(engine, engine.config.seed if hasattr(engine, 'config') and engine.config.seed is not None else 0, initial_population)
        traced_engine = _make_tracing_engine(engine, replay)
        traced_engine.run(initial_population)

        # Check non-decreasing max fitness (total preorder: f_i <= f_{i+1})
        violations = []
        for i in range(len(replay.events) - 1):
            # Get max fitness from scored population at each generation
            max_fitness_i = max(s["fitness"] for s in replay.events[i]["scored"])
            max_fitness_next = max(s["fitness"] for s in replay.events[i + 1]["scored"])
            if max_fitness_i > max_fitness_next + 1e-12:
                violations.append((i, max_fitness_i, max_fitness_next))

        max_fitnesses = [max(s["fitness"] for s in e["scored"]) for e in replay.events]
        return ContractResult(
            law_name="elitism",
            passed=len(violations) == 0,
            details={
                "max_fitnesses": max_fitnesses,
                "violations": violations,
            },
            counterexample=violations[0] if violations else None,
        )

    def check_population_invariance(
        self,
        engine: EvolutionEngine[GenomeT],
        initial_population: List[GenomeT],
    ) -> ContractResult:
        """Law 3: Population size constant per generation."""
        expected_size = len(initial_population)
        replay = DeterministicReplay(engine, engine.config.seed if hasattr(engine, 'config') and engine.config.seed is not None else 0, initial_population)
        traced_engine = _make_tracing_engine(engine, replay)
        traced_engine.run(initial_population)
        
        # Get population sizes from trace
        initial_hashes = [replay._hash_genome(g) for g in initial_population]
        sizes = [len(initial_hashes)]
        for e in replay.events:
            sizes.append(len(e["next_population_hashes"]))

        violations = [(i, s) for i, s in enumerate(sizes) if s != expected_size]

        return ContractResult(
            law_name="population_invariance",
            passed=len(violations) == 0,
            details={
                "expected_size": expected_size,
                "observed_sizes": sizes,
                "violations": violations,
            },
            counterexample=violations[0] if violations else None,
        )

    def check_archive_monotonicity(
        self,
        engine: EvolutionEngine[GenomeT],
        initial_population: List[GenomeT],
    ) -> ContractResult:
        """Law 4: Archive size never decreases."""
        replay = DeterministicReplay(engine, engine.config.seed if hasattr(engine, 'config') and engine.config.seed is not None else 0, initial_population)
        traced_engine = _make_tracing_engine(engine, replay)
        traced_engine.run(initial_population)

        archive_sizes = [e["summary"]["archive_size"] for e in replay.events]

        violations = []
        for i in range(len(archive_sizes) - 1):
            if archive_sizes[i] > archive_sizes[i + 1]:
                violations.append((i, archive_sizes[i], archive_sizes[i + 1]))

        return ContractResult(
            law_name="archive_monotonicity",
            passed=len(violations) == 0,
            details={
                "archive_sizes": archive_sizes,
                "violations": violations,
            },
            counterexample=violations[0] if violations else None,
        )

    def check_optimization_pressure(
        self,
        engine: EvolutionEngine[GenomeT],
        initial_population: List[GenomeT],
        num_samples: int = 1000,
    ) -> ContractResult:
        """Law 7: Optimization Pressure - Tournament selection by declared pressure must select better than random.
        
        Tests that tournament selection by declared optimization pressure (fitness for standard engines)
        selects better individuals than random selection.
        """
        # Run one generation to get scored population
        population = initial_population
        scored = engine._evaluate_population(population)

        if not scored:
            return ContractResult(
                law_name="optimization_pressure",
                passed=False,
                details={"error": "empty scored population"},
                counterexample="no candidates to select from",
            )

        # Compare tournament-by-fitness vs random selection
        tournament_fitnesses = []
        random_fitnesses = []

        tournament_size = engine.config.tournament_size

        for _ in range(num_samples):
            # Tournament selection by fitness (as implemented in engine)
            competitors = random.sample(scored, min(tournament_size, len(scored)))
            tournament_parent = max(competitors, key=lambda c: c.fitness)
            tournament_fitnesses.append(tournament_parent.fitness)

            # Random selection (baseline)
            random_parent = random.choice(scored)
            random_fitnesses.append(random_parent.fitness)

        tournament_mean = np.mean(tournament_fitnesses)
        random_mean = np.mean(random_fitnesses)

        # Selection pressure: tournament by fitness should select fitter than random
        # Allow small tolerance
        passed = tournament_mean >= random_mean - 1e-6

        return ContractResult(
            law_name="optimization_pressure",
            passed=passed,
            details={
                "tournament_mean_fitness": float(tournament_mean),
                "random_mean_fitness": float(random_mean),
                "difference": float(tournament_mean - random_mean),
                "num_samples": num_samples,
            },
            counterexample=f"Tournament mean={tournament_mean:.6f} < Random mean={random_mean:.6f}" if not passed else None,
        )

    def check_semantic_equivalence(
        self,
        engine_factory: Callable[[], EvolutionEngine[GenomeT]],
        initial_population: List[GenomeT],
        config: EvolutionConfig,
        distributed_backend: str = "thread",
    ) -> ContractResult:
        """Law 6: Distributed evaluation produces same evidence bundle as sequential."""
        from evolving_ai.runtime.distributed import (
            DistributedEvolutionEngine,
            DistributedEvolutionConfig,
            ThreadPoolBackend,
        )

        # Run sequential
        seq_engine = engine_factory()
        seq_replay = DeterministicReplay(seq_engine, config.seed or 0, initial_population)
        seq_traced = _make_tracing_engine(seq_engine, seq_replay)
        seq_traced.run(initial_population)
        seq_trace = seq_replay.get_trace()

        # Run distributed
        dist_config = DistributedEvolutionConfig(
            population_size=config.population_size,
            generations=config.generations,
            mutation_rate=config.mutation_rate,
            novelty_weight=config.novelty_weight,
            elite_fraction=config.elite_fraction,
            tournament_size=config.tournament_size,
            seed=config.seed,
            backend=distributed_backend,
            num_workers=2,
        )
        dist_engine = DistributedEvolutionEngine(dist_config, engine_factory().task, NoveltyArchive())
        dist_replay = DeterministicReplay(dist_engine, config.seed or 0, initial_population)
        dist_traced = _make_tracing_engine(dist_engine, dist_replay)
        dist_traced.run(initial_population)
        dist_trace = dist_replay.get_trace()

        # Compare semantic equivalence: same evidence bundle
        # (same best fitness trajectory, same archive growth, same final population semantics)
        seq_best_fitness = [e["summary"]["best_fitness"] for e in seq_trace.generation_events]
        dist_best_fitness = [e["summary"]["best_fitness"] for e in dist_trace.generation_events]

        seq_archive = [e["summary"]["archive_size"] for e in seq_trace.generation_events]
        dist_archive = [e["summary"]["archive_size"] for e in dist_trace.generation_events]

        fitness_match = np.allclose(seq_best_fitness, dist_best_fitness, atol=1e-6)
        archive_match = seq_archive == dist_archive

        passed = fitness_match and archive_match

        return ContractResult(
            law_name="semantic_equivalence",
            passed=passed,
            details={
                "seq_best_fitness": seq_best_fitness,
                "dist_best_fitness": dist_best_fitness,
                "seq_archive_sizes": seq_archive,
                "dist_archive_sizes": dist_archive,
                "fitness_match": fitness_match,
                "archive_match": archive_match,
            },
            counterexample="fitness trajectory or archive growth differs" if not passed else None,
        )


# TypeVar for the contract
GenomeT = TypeVar("GenomeT", bound=Genome)