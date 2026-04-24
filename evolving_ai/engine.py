from __future__ import annotations

from dataclasses import dataclass
import json
from pathlib import Path
import random
from typing import Callable

from .archive import NoveltyArchive
from .config import EvolutionConfig
from .genome import Genome
from .network import NeuralNetwork
from .tasks import EvolutionTask, TaskEvaluation


@dataclass(frozen=True, slots=True)
class EvaluatedCandidate:
    genome: Genome
    objective_score: float
    novelty_score: float
    combined_score: float
    behavior: tuple[float, ...]
    diagnostics: dict[str, float]

    def to_dict(self) -> dict[str, object]:
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

    def to_dict(self) -> dict[str, object]:
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
class EvolutionResult:
    task_name: str
    best: EvaluatedCandidate
    hall_of_fame: tuple[EvaluatedCandidate, ...]
    history: tuple[GenerationSummary, ...]
    archive_size: int

    def to_dict(self) -> dict[str, object]:
        return {
            "task_name": self.task_name,
            "best": self.best.to_dict(),
            "hall_of_fame": [candidate.to_dict() for candidate in self.hall_of_fame],
            "history": [summary.to_dict() for summary in self.history],
            "archive_size": self.archive_size,
        }


class EvolutionEngine:
    def __init__(self, task: EvolutionTask, config: EvolutionConfig) -> None:
        self.task = task
        self.config = config
        self.rng = random.Random(config.seed)
        self.archive = NoveltyArchive(k_neighbors=config.behavior_neighbors)
        self.hall_of_fame: list[EvaluatedCandidate] = []
        self.history: list[GenerationSummary] = []
        self.best_objective_seen = float("-inf")
        self.stagnation = 0

    def _initial_population(self) -> list[Genome]:
        return [
            Genome.random(
                shape=self.task.shape,
                rng=self.rng,
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
        return [(value - lower) / (upper - lower) for value in values]

    def _evaluate_population(
        self, population: list[Genome]
    ) -> list[EvaluatedCandidate]:
        evaluations: list[TaskEvaluation] = []
        for genome in population:
            network = NeuralNetwork.from_genome(self.task.shape, genome)
            evaluations.append(self.task.evaluate(network))

        behaviors = [evaluation.behavior for evaluation in evaluations]
        novelty_scores = [
            self.archive.score(
                behavior=evaluation.behavior,
                population_behaviors=behaviors[:index] + behaviors[index + 1 :],
            )
            for index, evaluation in enumerate(evaluations)
        ]
        normalized_novelty = self._normalize(novelty_scores)

        candidates = [
            EvaluatedCandidate(
                genome=genome,
                objective_score=evaluation.objective_score,
                novelty_score=novelty,
                combined_score=(
                    ((1.0 - self.config.novelty_weight) * evaluation.objective_score)
                    + (self.config.novelty_weight * novelty)
                ),
                behavior=evaluation.behavior,
                diagnostics=evaluation.diagnostics,
            )
            for genome, evaluation, novelty in zip(
                population, evaluations, normalized_novelty
            )
        ]

        return sorted(
            candidates,
            key=lambda candidate: (
                candidate.combined_score,
                candidate.objective_score,
                -candidate.genome.age,
            ),
            reverse=True,
        )

    def _select_parent(
        self, population: list[EvaluatedCandidate]
    ) -> EvaluatedCandidate:
        competitors = self.rng.sample(
            population, k=min(self.config.tournament_size, len(population))
        )
        return max(
            competitors,
            key=lambda candidate: (candidate.combined_score, candidate.objective_score),
        )

    def _update_hall_of_fame(self, candidates: list[EvaluatedCandidate]) -> None:
        objective_ranked = sorted(
            candidates,
            key=lambda candidate: (candidate.objective_score, candidate.combined_score),
            reverse=True,
        )
        self.hall_of_fame.extend(objective_ranked[: self.config.elite_count])
        self.hall_of_fame.sort(
            key=lambda candidate: (candidate.objective_score, candidate.combined_score),
            reverse=True,
        )

        unique: list[EvaluatedCandidate] = []
        seen: set[tuple[float, ...]] = set()
        for candidate in self.hall_of_fame:
            signature = candidate.genome.genes
            if signature in seen:
                continue
            seen.add(signature)
            unique.append(candidate)
            if len(unique) == self.config.hall_of_fame_size:
                break
        self.hall_of_fame = unique

    def _refresh_archive(
        self, candidates: list[EvaluatedCandidate], generation: int
    ) -> None:
        by_novelty = sorted(
            candidates, key=lambda candidate: candidate.novelty_score, reverse=True
        )
        if by_novelty:
            self.archive.add(
                behavior=by_novelty[0].behavior,
                objective_score=by_novelty[0].objective_score,
                generation=generation,
            )

        for candidate in by_novelty[1:]:
            if self.rng.random() <= self.config.archive_probability:
                self.archive.add(
                    behavior=candidate.behavior,
                    objective_score=candidate.objective_score,
                    generation=generation,
                )

    def _generation_summary(
        self, generation: int, candidates: list[EvaluatedCandidate]
    ) -> GenerationSummary:
        average_objective = sum(c.objective_score for c in candidates) / len(candidates)
        average_novelty = sum(c.novelty_score for c in candidates) / len(candidates)
        best_objective = max(candidate.objective_score for candidate in candidates)
        summary = GenerationSummary(
            generation=generation,
            best_objective=best_objective,
            best_combined=candidates[0].combined_score,
            average_objective=average_objective,
            average_novelty=average_novelty,
            archive_size=len(self.archive.entries),
            stagnation=self.stagnation,
        )
        self.history.append(summary)
        return summary

    def _advance_stagnation(self, best_objective: float) -> bool:
        improved = best_objective > self.best_objective_seen + 1e-12
        if improved:
            self.best_objective_seen = best_objective
            self.stagnation = 0
        else:
            self.stagnation += 1
        return improved

    def _spawn_next_population(
        self, candidates: list[EvaluatedCandidate]
    ) -> list[Genome]:
        next_population = [
            candidate.genome.with_age(candidate.genome.age + 1)
            for candidate in candidates[: self.config.elite_count]
        ]

        injection_count = 0
        if self.stagnation >= self.config.stagnation_limit:
            injection_count = self.config.diversity_injection_count
            self.stagnation = 0

        target_offspring = self.config.population_size - injection_count
        while len(next_population) < target_offspring:
            first_parent = self._select_parent(candidates).genome
            if self.rng.random() <= self.config.crossover_rate:
                second_parent = self._select_parent(candidates).genome
                child = first_parent.crossover(second_parent, self.rng)
            else:
                child = first_parent
            child = child.mutate(self.config, self.rng)
            next_population.append(child)

        while len(next_population) < self.config.population_size:
            next_population.append(
                Genome.random(
                    shape=self.task.shape,
                    rng=self.rng,
                    mutation_scale=self.config.mutation_strength,
                )
            )

        return next_population

    def run(
        self,
        progress_callback: Callable[[GenerationSummary], None] | None = None,
    ) -> EvolutionResult:
        population = self._initial_population()

        for generation in range(self.config.generations):
            candidates = self._evaluate_population(population)
            self._advance_stagnation(
                max(candidate.objective_score for candidate in candidates)
            )
            self._update_hall_of_fame(candidates)
            self._refresh_archive(candidates, generation)
            summary = self._generation_summary(generation, candidates)
            if progress_callback is not None:
                progress_callback(summary)
            population = self._spawn_next_population(candidates)

        if not self.hall_of_fame:
            raise RuntimeError("Evolution finished without producing any candidates.")

        best = max(
            self.hall_of_fame,
            key=lambda candidate: (candidate.objective_score, candidate.combined_score),
        )
        return EvolutionResult(
            task_name=self.task.name,
            best=best,
            hall_of_fame=tuple(self.hall_of_fame),
            history=tuple(self.history),
            archive_size=len(self.archive.entries),
        )

    def save_result(self, path: str | Path, result: EvolutionResult) -> None:
        destination = Path(path)
        destination.parent.mkdir(parents=True, exist_ok=True)
        destination.write_text(json.dumps(result.to_dict(), indent=2), encoding="utf-8")
