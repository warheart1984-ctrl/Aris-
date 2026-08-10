from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Callable, Generic, List, TypeVar
import random

from .genome import Genome

GenomeT = TypeVar("GenomeT", bound=Genome)


@dataclass
class MutationConfig:
    mutation_probability: float = 0.18
    mutation_strength: float = 0.35


@dataclass
class EvolutionConfig:
    population_size: int = 96
    generations: int = 80
    mutation_rate: float = 0.18
    mutation_strength: float = 0.35
    novelty_weight: float = 0.25
    elite_fraction: float = 0.05
    tournament_size: int = 4
    seed: int | None = None

    def to_mutation_config(self) -> MutationConfig:
        return MutationConfig(
            mutation_probability=self.mutation_rate,
            mutation_strength=self.mutation_strength,
        )


@dataclass
class MutationConfig:
    mutation_probability: float = 0.18
    mutation_strength: float = 0.35


@dataclass
class EvaluatedCandidate(Generic[GenomeT]):
    genome: GenomeT
    fitness: float
    novelty: float
    score: float
    descriptor: Any


@dataclass
class GenerationSummary:
    generation: int
    best_fitness: float
    best_score: float
    avg_fitness: float
    avg_novelty: float
    archive_size: int


class EvolutionEngine(Generic[GenomeT]):
    def __init__(
        self,
        config: EvolutionConfig,
        task: Any,
        archive: Any,
        rng: random.Random | None = None,
    ) -> None:
        self.config = config
        self.task = task
        self.archive = archive
        self.rng = rng or random.Random(config.seed)

    def run(
        self,
        initial_population: List[GenomeT],
        progress_callback: Callable[[GenerationSummary], None] | None = None,
    ) -> EvaluatedCandidate[GenomeT]:
        population = initial_population
        best: EvaluatedCandidate[GenomeT] | None = None

        for gen in range(self.config.generations):
            scored = self._evaluate_population(population)
            best = max(scored, key=lambda s: s.score)
            population = self._next_generation(scored)

            if progress_callback:
                avg_fit = sum(s.fitness for s in scored) / len(scored)
                avg_nov = sum(s.novelty for s in scored) / len(scored)
                summary = GenerationSummary(
                    generation=gen,
                    best_fitness=best.fitness,
                    best_score=best.score,
                    avg_fitness=avg_fit,
                    avg_novelty=avg_nov,
                    archive_size=len(self.archive.entries) if hasattr(self.archive, 'entries') else len(getattr(self.archive, 'bins', {})),
                )
                progress_callback(summary)

        if best is None:
            raise RuntimeError("Evolution finished without producing any candidates.")
        return best

    def _evaluate_population(self, population: List[GenomeT]) -> List[EvaluatedCandidate[GenomeT]]:
        scored: List[EvaluatedCandidate[GenomeT]] = []
        for genome in population:
            fitness = self.task.evaluate(genome)
            descriptor = self.task.behavior_descriptor(genome)
            novelty = self.archive.novelty(descriptor)
            blended = (1.0 - self.config.novelty_weight) * fitness + \
                      self.config.novelty_weight * novelty
            self.archive.add(descriptor, fitness, genome)
            scored.append(EvaluatedCandidate(
                genome=genome,
                fitness=fitness,
                novelty=novelty,
                score=blended,
                descriptor=descriptor,
            ))
        return scored

    def _next_generation(self, scored: List[EvaluatedCandidate[GenomeT]]) -> List[GenomeT]:
        scored.sort(key=lambda s: s.score, reverse=True)
        n = len(scored)
        elite_count = max(1, int(self.config.elite_fraction * n))
        
        # Global elite preservation - preserve the max-fitness individual
        global_best_fitness = max(scored, key=lambda c: c.fitness).genome.clone()
        elites = [global_best_fitness]
        
        # Add top-score elites (avoid duplicating global best)
        for s in scored[:elite_count]:
            if s.genome is not global_best_fitness:
                elites.append(s.genome.clone())

        def tournament() -> GenomeT:
            candidates = self.rng.sample(scored, min(self.config.tournament_size, len(scored)))
            return max(candidates, key=lambda s: s.fitness).genome

        new_pop: List[GenomeT] = elites[:]
        mut_config = self.config.to_mutation_config()
        while len(new_pop) < n:
            parent1 = tournament()
            parent2 = tournament()
            child = parent1.crossover(parent2, self.rng)
            if self.rng.random() < self.config.mutation_rate:
                child = child.mutate(mut_config, self.rng)
            new_pop.append(child)
        return new_pop