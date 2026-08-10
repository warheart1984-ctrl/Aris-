from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Callable
import json
import numpy as np
from pathlib import Path

from . import (
    EvolutionEngine,
    EvolutionConfig,
    EvolutionResult,
    EvaluatedCandidate,
    GenerationSummary,
    SelectionStrategy,
)
from ..genomes import Genome, VectorGenome, NeuralNetwork, NetworkShape, MutationConfig
from ..archives import Archive, NoveltyArchive
from ..tasks import Task, TaskEvaluation


@dataclass
class StandardEvolutionEngine(EvolutionEngine[VectorGenome, NeuralNetwork]):
    task: Task
    config: EvolutionConfig
    _rng: np.random.Generator = field(init=False)
    _archive: NoveltyArchive = field(init=False)
    _hall_of_fame: list[EvaluatedCandidate[VectorGenome]] = field(default_factory=list, init=False)
    _history: list[GenerationSummary] = field(default_factory=list, init=False)
    _best_objective_seen: float = field(default=float("-inf"), init=False)
    _stagnation: int = field(default=0, init=False)

    def __post_init__(self) -> None:
        seed = self.config.seed if self.config.seed is not None else np.random.SeedSequence().entropy
        self._rng = np.random.default_rng(seed)
        self._archive = NoveltyArchive(k_neighbors=self.config.behavior_neighbors)

    def _initial_population(self) -> list[VectorGenome]:
        return [
            VectorGenome.random(
                shape=self.task.shape,
                rng=self._rng,
                mutation_scale=self.config.mutation_strength,
            )
            for _ in range(self.config.population_size)
        ]

    def _normalize(self, values: list[float]) -> list[float]:
        if not values:
            return []
        lower = min(values)
        upper = max(values)
        if upper - lower < 1e-12:
            return [0.0 for _ in values]
        return [(v - lower) / (upper - lower) for v in values]

    def _evaluate_population(self, population: list[VectorGenome]) -> list[EvaluatedCandidate[VectorGenome]]:
        evaluations: list[TaskEvaluation] = []
        for genome in population:
            network = NeuralNetwork.from_genome(self.task.shape, genome)
            evaluations.append(self.task.evaluate(network))

        behaviors = [e.behavior for e in evaluations]
        novelty_scores = [
            self._archive.score(
                behavior=e.behavior,
                population_behaviors=behaviors[:i] + behaviors[i+1:],
            )
            for i, e in enumerate(evaluations)
        ]
        normalized_novelty = self._normalize(novelty_scores)

        candidates = [
            EvaluatedCandidate(
                genome=genome,
                objective_score=evaluation.objective_score,
                novelty_score=novelty,
                combined_score=(
                    (1.0 - self.config.novelty_weight) * evaluation.objective_score
                    + self.config.novelty_weight * novelty
                ),
                behavior=evaluation.behavior,
                diagnostics=evaluation.diagnostics,
            )
            for genome, evaluation, novelty in zip(population, evaluations, normalized_novelty)
        ]

        return sorted(
            candidates,
            key=lambda c: (c.combined_score, c.objective_score, -c.genome.age),
            reverse=True,
        )

    def _select_parent(self, candidates: list[EvaluatedCandidate[VectorGenome]]) -> EvaluatedCandidate[VectorGenome]:
        competitors = self._rng.choice(
            candidates,
            size=min(self.config.tournament_size, len(candidates)),
            replace=False,
        )
        return max(competitors, key=lambda c: (c.combined_score, c.objective_score))

    def _update_hall_of_fame(self, candidates: list[EvaluatedCandidate[VectorGenome]]) -> None:
        objective_ranked = sorted(
            candidates,
            key=lambda c: (c.objective_score, c.combined_score),
            reverse=True,
        )
        self._hall_of_fame.extend(objective_ranked[:self.config.elite_count])
        self._hall_of_fame.sort(
            key=lambda c: (c.objective_score, c.combined_score),
            reverse=True,
        )

        unique: list[EvaluatedCandidate[VectorGenome]] = []
        seen: set[tuple[float, ...]] = set()
        for c in self._hall_of_fame:
            sig = c.genome.genes
            if sig in seen:
                continue
            seen.add(sig)
            unique.append(c)
            if len(unique) == self.config.hall_of_fame_size:
                break
        self._hall_of_fame = unique

    def _refresh_archive(self, candidates: list[EvaluatedCandidate[VectorGenome]], generation: int) -> None:
        by_novelty = sorted(candidates, key=lambda c: c.novelty_score, reverse=True)
        if by_novelty:
            self._archive.add(
                behavior=by_novelty[0].behavior,
                objective_score=by_novelty[0].objective_score,
                generation=generation,
            )
        for c in by_novelty[1:]:
            if self._rng.random() <= self.config.archive_probability:
                self._archive.add(
                    behavior=c.behavior,
                    objective_score=c.objective_score,
                    generation=generation,
                )

    def _generation_summary(self, generation: int, candidates: list[EvaluatedCandidate[VectorGenome]]) -> GenerationSummary:
        avg_obj = sum(c.objective_score for c in candidates) / len(candidates)
        avg_nov = sum(c.novelty_score for c in candidates) / len(candidates)
        best_obj = max(c.objective_score for c in candidates)
        summary = GenerationSummary(
            generation=generation,
            best_objective=best_obj,
            best_combined=candidates[0].combined_score,
            average_objective=avg_obj,
            average_novelty=avg_nov,
            archive_size=len(self._archive.entries),
            stagnation=self._stagnation,
        )
        self._history.append(summary)
        return summary

    def _advance_stagnation(self, best_objective: float) -> bool:
        improved = best_objective > self._best_objective_seen + 1e-12
        if improved:
            self._best_objective_seen = best_objective
            self._stagnation = 0
        else:
            self._stagnation += 1
        return improved

    def _spawn_next_population(self, candidates: list[EvaluatedCandidate[VectorGenome]]) -> list[VectorGenome]:
        next_pop = [
            c.genome.with_age(c.genome.age + 1)
            for c in candidates[:self.config.elite_count]
        ]

        injection_count = 0
        if self._stagnation >= self.config.stagnation_limit:
            injection_count = self.config.diversity_injection_count
            self._stagnation = 0

        target_offspring = self.config.population_size - injection_count
        mut_config = self.config.to_mutation_config()

        while len(next_pop) < target_offspring:
            parent1 = self._select_parent(candidates).genome
            if self._rng.random() <= self.config.crossover_rate:
                parent2 = self._select_parent(candidates).genome
                child = parent1.crossover(parent2, self._rng)
            else:
                child = parent1
            child = child.mutate(mut_config, self._rng)
            next_pop.append(child)

        while len(next_pop) < self.config.population_size:
            next_pop.append(
                VectorGenome.random(
                    shape=self.task.shape,
                    rng=self._rng,
                    mutation_scale=self.config.mutation_strength,
                )
            )

        return next_pop

    def run(
        self,
        progress_callback: Callable[[GenerationSummary], None] | None = None,
    ) -> EvolutionResult[VectorGenome]:
        population = self._initial_population()

        for generation in range(self.config.generations):
            candidates = self._evaluate_population(population)
            self._advance_stagnation(max(c.objective_score for c in candidates))
            self._update_hall_of_fame(candidates)
            self._refresh_archive(candidates, generation)
            summary = self._generation_summary(generation, candidates)
            if progress_callback:
                progress_callback(summary)
            population = self._spawn_next_population(candidates)

        if not self._hall_of_fame:
            raise RuntimeError("Evolution finished without producing any candidates.")

        best = max(
            self._hall_of_fame,
            key=lambda c: (c.objective_score, c.combined_score),
        )
        return EvolutionResult(
            task_name=self.task.name,
            best=best,
            hall_of_fame=tuple(self._hall_of_fame),
            history=tuple(self._history),
            archive_size=len(self._archive.entries),
        )

    def save_result(self, path: str, result: EvolutionResult[VectorGenome]) -> None:
        dest = Path(path)
        dest.parent.mkdir(parents=True, exist_ok=True)
        dest.write_text(json.dumps(result.to_dict(), indent=2), encoding="utf-8")


def tournament_selection(
    population: list[EvaluatedCandidate],
    tournament_size: int,
    rng: np.random.Generator,
) -> EvaluatedCandidate:
    competitors = rng.choice(population, size=min(tournament_size, len(population)), replace=False)
    return max(competitors, key=lambda c: (c.combined_score, c.objective_score))