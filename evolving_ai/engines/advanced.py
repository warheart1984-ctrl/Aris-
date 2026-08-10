from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any, Callable, Generic, List, TypeVar
import random
import math

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
from evolving_ai.core.engine import MutationConfig

GenomeT = TypeVar("GenomeT", bound=Genome)


class SpeciationEngine(EvolutionEngine[GenomeT]):
    """NEAT-style speciation engine with explicit species protection."""

    def __init__(
        self,
        config: EvolutionConfig,
        task: Task,
        archive: Archive,
        compatibility_threshold: float = 3.0,
        compatibility_coefficients: tuple[float, float, float] = (1.0, 1.0, 0.4),
        target_species: int = 10,
        survival_threshold: float = 0.2,
        rng: random.Random | None = None,
    ) -> None:
        super().__init__(config, task, archive, rng)
        self.compatibility_threshold = compatibility_threshold
        self.c1, self.c2, self.c3 = compatibility_coefficients
        self.target_species = target_species
        self.survival_threshold = survival_threshold
        self.species: List[List[GenomeT]] = []
        self.species_ages: List[int] = []
        self.species_best_fitness: List[float] = []
        self.generation = 0

    def _compatibility_distance(self, g1: GenomeT, g2: GenomeT) -> float:
        """NEAT compatibility distance: disjoint/excess genes + weight diff."""
        if hasattr(g1, 'weights') and hasattr(g2, 'weights'):
            w1, w2 = np.array(g1.weights), np.array(g2.weights)
            if len(w1) != len(w2):
                return float('inf')
            weight_diff = np.mean(np.abs(w1 - w2))
            return self.c3 * weight_diff
        return float('inf')

    def _speciate(self, population: List[GenomeT]) -> None:
        """Assign each genome to a species."""
        new_species: List[List[GenomeT]] = []
        new_ages: List[int] = []
        new_best: List[float] = []

        for genome in population:
            placed = False
            for i, species in enumerate(self.species):
                rep = species[0]
                if self._compatibility_distance(genome, rep) < self.compatibility_threshold:
                    species.append(genome)
                    placed = True
                    break
            if not placed:
                new_species.append([genome])
                new_ages.append(0)
                new_best.append(-float('inf'))

        # Update existing species ages and best fitness
        for i, species in enumerate(self.species):
            if species:
                best_fit = max(self.task.evaluate(g) for g in species)
                if i < len(self.species_best_fitness):
                    if best_fit > self.species_best_fitness[i]:
                        self.species_best_fitness[i] = best_fit
                        self.species_ages[i] = 0
                    else:
                        self.species_ages[i] += 1
                else:
                    self.species_best_fitness.append(best_fit)
                    self.species_ages.append(0)

        self.species = [s for s in self.species if s]
        self.species_ages = self.species_ages[:len(self.species)]
        self.species_best_fitness = self.species_best_fitness[:len(self.species)]

    def _adjusted_fitness(self, candidates: List[EvaluatedCandidate[GenomeT]]) -> List[float]:
        """Fitness sharing within species."""
        species_map: dict[int, List[EvaluatedCandidate[GenomeT]]] = {}
        for c in candidates:
            species_id = -1
            for i, species in enumerate(self.species):
                if any(g is c.genome for g in species):
                    species_id = i
                    break
            if species_id not in species_map:
                species_map[species_id] = []
            species_map[species_id].append(c)

        adjusted = []
        for c in candidates:
            species_id = -1
            for i, species in enumerate(self.species):
                if any(g is c.genome for g in species):
                    species_id = i
                    break
            if species_id >= 0 and species_id in species_map:
                share = len(species_map[species_id])
                adjusted.append(c.fitness / max(1, share))
            else:
                adjusted.append(c.fitness)
        return adjusted

    def _next_generation(self, scored: List[EvaluatedCandidate[GenomeT]]) -> List[GenomeT]:
        self.generation += 1

        # Speciate
        population = [c.genome for c in scored]
        self._speciate(population)

        # Adjust threshold to target species count
        if len(self.species) < self.target_species:
            self.compatibility_threshold *= 0.95
        elif len(self.species) > self.target_species:
            self.compatibility_threshold *= 1.05
        self.compatibility_threshold = max(0.1, min(10.0, self.compatibility_threshold))

        # Remove stale species
        self.species = [
            s for i, s in enumerate(self.species)
            if self.species_ages[i] < 20 or self.species_best_fitness[i] == max(self.species_best_fitness)
        ]
        self.species_ages = self.species_ages[:len(self.species)]
        self.species_best_fitness = self.species_best_fitness[:len(self.species)]

        # Calculate offspring per species
        total_adj_fit = sum(self._adjusted_fitness(scored))
        offspring_counts = []
        for i, species in enumerate(self.species):
            species_adj = sum(
                af for c, af in zip(scored, self._adjusted_fitness(scored))
                if any(g is c.genome for g in species)
            )
            count = max(1, int((species_adj / total_adj_fit) * self.config.population_size))
            offspring_counts.append(count)

        # Normalize
        while sum(offspring_counts) > self.config.population_size:
            idx = offspring_counts.index(max(offspring_counts))
            offspring_counts[idx] -= 1

        # Breed within species
        new_pop: List[GenomeT] = []
        mut_config = self.config.to_mutation_config()

        # Global elite preservation - preserve the overall best-by-fitness individual
        global_best_fitness = max(scored, key=lambda c: c.fitness).genome.clone()
        new_pop.append(global_best_fitness)

        for i, species in enumerate(self.species):
            if not species:
                continue
            species_candidates = [
                c for c in scored if any(g is c.genome for g in species)
            ]
            species_candidates.sort(key=lambda c: c.score, reverse=True)

            # Elites (per species)
            elite_count = max(1, int(len(species) * self.config.elite_fraction))
            for c in species_candidates[:elite_count]:
                # Avoid duplicating global best
                if c.genome is not global_best_fitness:                   new_pop.append(c.genome.clone())

            # Offspring
            while len(new_pop) < sum(offspring_counts[:i+1]) and len(new_pop) < self.config.population_size:
                if len(species_candidates) < 2:
                    break
                p1 = self._tournament(species_candidates).genome
                p2 = self._tournament(species_candidates).genome
                child = p1.crossover(p2, self.rng)
                if self.rng.random() < self.config.mutation_rate:
                    child = child.mutate(mut_config, self.rng)
                new_pop.append(child)

        # Fill remaining
        while len(new_pop) < self.config.population_size:
            genome_size = len(population[0].weights) if population and hasattr(population[0], 'weights') else 100
            new_pop.append(DenseGenome.random(
                genome_size,
                self.config.mutation_strength,
                self.rng
            ))

        return new_pop[:self.config.population_size]

    def _tournament(self, candidates: List[EvaluatedCandidate]) -> EvaluatedCandidate:
        comp = self.rng.sample(candidates, min(self.config.tournament_size, len(candidates)))
        return max(comp, key=lambda c: c.fitness)

    def run(
        self,
        initial_population: List[GenomeT],
        progress_callback: Callable[[GenerationSummary], None] | None = None,
    ) -> EvaluatedCandidate[GenomeT]:
        # Initialize species
        self.species = [[g] for g in initial_population]
        self.species_ages = [0] * len(initial_population)
        self.species_best_fitness = [-float('inf')] * len(initial_population)
        return super().run(initial_population, progress_callback)


class MapElitesEngine(EvolutionEngine[GenomeT]):
    """MAP-Elites quality-diversity engine."""

    def __init__(
        self,
        config: EvolutionConfig,
        task: Task,
        archive: Archive,
        feature_dims: int = 2,
        grid_size: int = 10,
        feature_min: tuple[float, ...] = (0.0, 0.0),
        feature_max: tuple[float, ...] = (1.0, 1.0),
        rng: random.Random | None = None,
    ) -> None:
        super().__init__(config, task, archive, rng)
        self.feature_dims = feature_dims
        self.grid_size = grid_size
        self.feature_min = feature_min
        self.feature_max = feature_max
        self.grid: dict[tuple[int, ...], tuple[float, GenomeT, tuple[float, ...]]] = {}

    def _bin_index(self, descriptor: tuple[float, ...]) -> tuple[int, ...]:
        idx = []
        for i, val in enumerate(descriptor):
            if i >= len(self.feature_min) or i >= len(self.feature_max):
                idx.append(0)
                continue
            if self.feature_max[i] == self.feature_min[i]:
                idx.append(0)
            else:
                norm = (val - self.feature_min[i]) / (self.feature_max[i] - self.feature_min[i])
                norm = max(0.0, min(1.0, norm))
                idx.append(int(norm * (self.grid_size - 1)))
        return tuple(idx[:self.feature_dims])

    def _evaluate_population(self, population: List[GenomeT]) -> List[EvaluatedCandidate[GenomeT]]:
        scored = super()._evaluate_population(population)
        for c in scored:
            idx = self._bin_index(c.descriptor)
            if idx not in self.grid or c.fitness > self.grid[idx][0]:
                self.grid[idx] = (c.fitness, c.genome, c.descriptor)
        return scored

    def _next_generation(self, scored: List[EvaluatedCandidate[GenomeT]]) -> List[GenomeT]:
        # Sample parents from elite grid
        elites = list(self.grid.values())
        if not elites:
            return super()._next_generation(scored)

        new_pop: List[GenomeT] = []

        # Keep some elites directly
        elite_count = max(1, int(self.config.population_size * self.config.elite_fraction))
        for fit, genome, desc in sorted(elites, key=lambda x: x[0], reverse=True)[:elite_count]:
            new_pop.append(genome.clone())

        # Mutate elites for exploration
        mut_config = self.config.to_mutation_config() if hasattr(self.config, 'to_mutation_config') else None
        while len(new_pop) < self.config.population_size:
            fit, parent, desc = self.rng.choice(elites)
            child = parent.clone()
            if self.rng.random() < self.config.mutation_rate:
                if mut_config:
                    child = child.mutate(mut_config, self.rng)
                else:
                    child = child.mutate(self.rng)
            new_pop.append(child)

        return new_pop[:self.config.population_size]

    def get_elites(self) -> List[tuple[tuple[int, ...], float, GenomeT, tuple[float, ...]]]:
        return [(idx, fit, gen, desc) for idx, (fit, gen, desc) in self.grid.items()]


class NSGA2Engine(EvolutionEngine[GenomeT]):
    """NSGA-II multi-objective evolution engine."""

    def __init__(
        self,
        config: EvolutionConfig,
        task: Task,
        archive: Archive,
        objectives: List[Callable[[GenomeT], float]] | None = None,
        rng: random.Random | None = None,
    ) -> None:
        super().__init__(config, task, archive, rng)
        self.objectives = objectives or [lambda g: task.evaluate(g)]

    def _dominates(self, a: List[float], b: List[float]) -> bool:
        """Check if a dominates b (all objectives better or equal, at least one strictly)."""
        return all(x <= y for x, y in zip(a, b)) and any(x < y for x, y in zip(a, b))

    def _fast_non_dominated_sort(
        self,
        candidates: List[EvaluatedCandidate[GenomeT]],
    ) -> List[List[EvaluatedCandidate[GenomeT]]]:
        """Return fronts (list of lists)."""
        n = len(candidates)
        dominated_count = [0] * n
        dominates_list = [[] for _ in range(n)]
        fronts = [[]]

        for i in range(n):
            obj_i = self._get_objectives(candidates[i].genome)
            for j in range(n):
                if i == j:
                    continue
                obj_j = self._get_objectives(candidates[j].genome)
                if self._dominates(obj_i, obj_j):
                    dominates_list[i].append(j)
                elif self._dominates(obj_j, obj_i):
                    dominated_count[i] += 1
            if dominated_count[i] == 0:
                fronts[0].append(candidates[i])

        front_idx = 0
        while front_idx < len(fronts) and fronts[front_idx]:
            next_front = []
            for i_cand in fronts[front_idx]:
                i = candidates.index(i_cand)
                for j in dominates_list[i]:
                    dominated_count[j] -= 1
                    if dominated_count[j] == 0:
                        next_front.append(candidates[j])
            front_idx += 1
            if next_front:
                fronts.append(next_front)
        return fronts

    def _get_objectives(self, genome: GenomeT) -> List[float]:
        return [obj(genome) for obj in self.objectives]

    def _crowding_distance(
        self,
        front: List[EvaluatedCandidate[GenomeT]],
    ) -> List[float]:
        if len(front) <= 2:
            return [float('inf')] * len(front)

        distances = [0.0] * len(front)
        n_obj = len(self.objectives)

        for m in range(n_obj):
            sorted_front = sorted(front, key=lambda c: self._get_objectives(c.genome)[m])
            distances[0] = float('inf')
            distances[-1] = float('inf')

            obj_min = self._get_objectives(sorted_front[0].genome)[m]
            obj_max = self._get_objectives(sorted_front[-1].genome)[m]
            if obj_max == obj_min:
                continue

            for i in range(1, len(sorted_front) - 1):
                prev_obj = self._get_objectives(sorted_front[i-1].genome)[m]
                next_obj = self._get_objectives(sorted_front[i+1].genome)[m]
                distances[front.index(sorted_front[i])] += (next_obj - prev_obj) / (obj_max - obj_min)

        return distances

    def _next_generation(self, scored: List[EvaluatedCandidate[GenomeT]]) -> List[GenomeT]:
        fronts = self._fast_non_dominated_sort(scored)

        new_pop: List[GenomeT] = []
        for front in fronts:
            if len(new_pop) + len(front) <= self.config.population_size:
                new_pop.extend([c.genome.clone() for c in front])
            else:
                # Crowding distance selection
                distances = self._crowding_distance(front)
                sorted_front = sorted(zip(front, distances), key=lambda x: x[1], reverse=True)
                needed = self.config.population_size - len(new_pop)
                new_pop.extend([c.genome.clone() for c, _ in sorted_front[:needed]])
                break

        # Fill with offspring
        mut_config = self.config.to_mutation_config() if hasattr(self.config, 'to_mutation_config') else None
        while len(new_pop) < self.config.population_size:
            p1 = self._tournament(scored).genome
            p2 = self._tournament(scored).genome
            child = p1.crossover(p2, self.rng)
            if self.rng.random() < self.config.mutation_rate:
                if mut_config:
                    child = child.mutate(mut_config, self.rng)
                else:
                    child = child.mutate(self.rng)
            new_pop.append(child)

        return new_pop[:self.config.population_size]

    def _tournament(self, candidates: List[EvaluatedCandidate]) -> EvaluatedCandidate:
        comp = self.rng.sample(candidates, min(self.config.tournament_size, len(candidates)))
        # NSGA-II tournament: compare rank then crowding distance
        fronts = self._fast_non_dominated_sort(comp)
        for front in fronts:
            if len(front) == 1:
                return front[0]
            distances = self._crowding_distance(front)
            return max(zip(front, distances), key=lambda x: x[1])[0]
        return comp[0]


class CMAESEngine(EvolutionEngine[GenomeT]):
    """CMA-ES (Covariance Matrix Adaptation Evolution Strategy) engine."""

    def __init__(
        self,
        config: EvolutionConfig,
        task: Task,
        archive: Archive,
        sigma: float = 0.5,
        population_size: int | None = None,
        rng: random.Random | None = None,
    ) -> None:
        super().__init__(config, task, archive, rng)
        self.sigma = sigma
        self.lambda_ = population_size or config.population_size
        self.mu = self.lambda_ // 2
        self.weights = [math.log(self.mu + 0.5) - math.log(i + 1) for i in range(self.mu)]
        weight_sum = sum(self.weights)
        self.weights = [w / weight_sum for w in self.weights]
        self.mueff = 1.0 / sum(w * w for w in self.weights)

        # CMA-ES parameters
        self.cc = (4 + self.mueff / self.config.population_size) / (self.config.population_size + 4 + 2 * self.mueff / self.config.population_size)
        self.cs = (self.mueff + 2) / (self.config.population_size + self.mueff + 5)
        self.c1 = 2 / ((self.config.population_size + 1.3) ** 2 + self.mueff)
        self.cmu = min(1 - self.c1, 2 * (self.mueff - 2 + 1 / self.mueff) / ((self.config.population_size + 2) ** 2 + self.mueff))
        self.damps = 1 + 2 * max(0, math.sqrt((self.mueff - 1) / (self.config.population_size + 1)) - 1) + self.cs

        self.mean: np.ndarray | None = None
        self.C: np.ndarray | None = None
        self.pc: np.ndarray | None = None
        self.ps: np.ndarray | None = None
        self._cma_initialized = False
        self._np_rng = np.random.default_rng(self.rng.randint(0, 2**32 - 1))
        self.generation = 0

    def _init_cma(self, genome: GenomeT) -> None:
        if not hasattr(genome, 'weights'):
            raise ValueError("CMA-ES requires genomes with 'weights' attribute")
        n = len(genome.weights)
        self.mean = np.array(genome.weights, dtype=float)
        self.C = np.eye(n)
        self.pc = np.zeros(n)
        self.ps = np.zeros(n)
        self._cma_initialized = True

    def _sample_population(self) -> List[np.ndarray]:
        if not self._cma_initialized or self.mean is None:
            return []
        try:
            samples = self._np_rng.multivariate_normal(self.mean, self.sigma ** 2 * self.C, self.lambda_)
        except np.linalg.LinAlgError:
            # Add jitter if not positive definite
            C_reg = self.C + 1e-12 * np.eye(len(self.C))
            samples = self._np_rng.multivariate_normal(self.mean, self.sigma ** 2 * C_reg, self.lambda_)
        return list(samples)

    def _update_cma(self, solutions: List[tuple[np.ndarray, float]]) -> None:
        """Update CMA-ES parameters from evaluated solutions."""
        if not self._cma_initialized or self.mean is None:
            return

        # Sort by fitness (ascending for minimization)
        solutions.sort(key=lambda x: x[1])
        selected = solutions[:self.mu]

        # Update mean
        old_mean = self.mean.copy()
        self.mean = np.zeros_like(self.mean)
        for w, (x, _) in zip(self.weights, selected):
            self.mean += w * x

        # Evolution paths
        y = (self.mean - old_mean) / self.sigma
        self.ps = (1 - self.cs) * self.ps + math.sqrt(self.cs * (2 - self.cs) * self.mueff) * y

        # Handle generation 0 case for hsig calculation
        if self.generation == 0:
            hsig = 1.0
        else:
            hsig = 1.0 if np.linalg.norm(self.ps) / math.sqrt(1 - (1 - self.cs) ** (2 * self.generation)) < (1.4 + 2 / (self.config.population_size + 1)) else 0.0

        self.pc = (1 - self.cc) * self.pc + hsig * math.sqrt(self.cc * (2 - self.cc) * self.mueff) * y

        # Covariance matrix
        self.C = (1 - self.c1 - self.cmu) * self.C
        self.C += self.c1 * np.outer(self.pc, self.pc)
        if hsig:
            self.C += self.c1 * self.cc * (2 - self.cc) * np.eye(len(self.C))

        for w, (x, _) in zip(self.weights, selected):
            y = (x - old_mean) / self.sigma
            self.C += self.cmu * w * np.outer(y, y)

        # Step size update
        self.sigma *= math.exp((self.cs / self.damps) * (np.linalg.norm(self.ps) / math.sqrt(self.config.population_size) - 1))

        self.generation += 1

    def run(
        self,
        initial_population: List[GenomeT],
        progress_callback: Callable[[GenerationSummary], None] | None = None,
    ) -> EvaluatedCandidate[GenomeT]:
        if not initial_population:
            raise RuntimeError("CMA-ES requires non-empty initial population")
        
        # Initialize CMA-ES from first genome
        self._init_cma(initial_population[0])

        best_candidate: EvaluatedCandidate[GenomeT] | None = None

        for gen in range(self.config.generations):
            # Sample new population
            samples = self._sample_population()
            population = []
            for sample in samples:
                # Create genome from sample - assume DenseGenome with weights
                genome = DenseGenome(
                    weights=sample.tolist(),
                    mutation_scale=self.config.mutation_strength,
                    lineage_id=f"cma_{gen}_{len(population)}",
                )
                population.append(genome)

            # Evaluate
            scored = self._evaluate_population(population)
            best_candidate = max(scored, key=lambda s: s.score)

            # Prepare for CMA-ES update (minimize -fitness)
            solutions = [(np.array(g.weights), -c.fitness) for g, c in zip(population, scored)]
            self._update_cma(solutions)

            if progress_callback:
                avg_fit = sum(s.fitness for s in scored) / len(scored)
                avg_nov = sum(s.novelty for s in scored) / len(scored)
                summary = GenerationSummary(
                    generation=gen,
                    best_fitness=best_candidate.fitness,
                    best_score=best_candidate.score,
                    avg_fitness=avg_fit,
                    avg_novelty=avg_nov,
                    archive_size=len(self.archive.entries) if hasattr(self.archive, 'entries') else 0,
                )
                progress_callback(summary)

        if best_candidate is None:
            raise RuntimeError("CMA-ES finished without candidates.")
        return best_candidate

    def _next_generation(self, scored: List[EvaluatedCandidate[GenomeT]]) -> List[GenomeT]:
        # Not used in CMA-ES (handled in run)
        return [c.genome for c in scored]