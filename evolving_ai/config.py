from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

ActivationName = Literal["relu", "sigmoid", "tanh"]


@dataclass(frozen=True, slots=True)
class NetworkShape:
    input_size: int
    hidden_layers: tuple[int, ...]
    output_size: int
    activation: ActivationName = "tanh"
    output_activation: ActivationName = "sigmoid"

    def __post_init__(self) -> None:
        layer_sizes = (self.input_size, *self.hidden_layers, self.output_size)
        if any(size <= 0 for size in layer_sizes):
            raise ValueError("All layer sizes must be positive integers.")

    @property
    def layer_sizes(self) -> tuple[int, ...]:
        return (self.input_size, *self.hidden_layers, self.output_size)

    @property
    def parameter_count(self) -> int:
        total = 0
        for input_width, output_width in zip(self.layer_sizes, self.layer_sizes[1:]):
            total += (input_width * output_width) + output_width
        return total


@dataclass(frozen=True, slots=True)
class EvolutionConfig:
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

    def __post_init__(self) -> None:
        if self.population_size < 4:
            raise ValueError("population_size must be at least 4.")
        if self.generations < 1:
            raise ValueError("generations must be at least 1.")
        if not 0.0 <= self.elite_fraction < 1.0:
            raise ValueError("elite_fraction must be in [0, 1).")
        if not 0.0 <= self.crossover_rate <= 1.0:
            raise ValueError("crossover_rate must be in [0, 1].")
        if not 0.0 <= self.mutation_probability <= 1.0:
            raise ValueError("mutation_probability must be in [0, 1].")
        if self.mutation_strength <= 0.0:
            raise ValueError("mutation_strength must be positive.")
        if self.mutation_scale_learning_rate <= 0.0:
            raise ValueError("mutation_scale_learning_rate must be positive.")
        if self.tournament_size < 2:
            raise ValueError("tournament_size must be at least 2.")
        if not 0.0 <= self.novelty_weight <= 1.0:
            raise ValueError("novelty_weight must be in [0, 1].")
        if not 0.0 <= self.archive_probability <= 1.0:
            raise ValueError("archive_probability must be in [0, 1].")
        if self.behavior_neighbors < 1:
            raise ValueError("behavior_neighbors must be at least 1.")
        if self.stagnation_limit < 1:
            raise ValueError("stagnation_limit must be at least 1.")
        if not 0.0 <= self.diversity_injection_fraction < 1.0:
            raise ValueError("diversity_injection_fraction must be in [0, 1).")
        if self.hall_of_fame_size < 1:
            raise ValueError("hall_of_fame_size must be at least 1.")

    @property
    def elite_count(self) -> int:
        return max(1, int(self.population_size * self.elite_fraction))

    @property
    def diversity_injection_count(self) -> int:
        return int(self.population_size * self.diversity_injection_fraction)
