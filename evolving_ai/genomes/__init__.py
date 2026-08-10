from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any, Generic, Protocol, TypeVar
import numpy as np

from ..config import ConfigBase

GenomeT = TypeVar("GenomeT", bound="Genome")
PhenotypeT = TypeVar("PhenotypeT")


class Genome(ABC, Generic[PhenotypeT]):
    @abstractmethod
    def mutate(self, config: "MutationConfig", rng: np.random.Generator) -> "Genome":
        pass

    @abstractmethod
    def crossover(self, other: "Genome", rng: np.random.Generator) -> "Genome":
        pass

    @abstractmethod
    def distance(self, other: "Genome") -> float:
        pass

    @abstractmethod
    def to_phenotype(self) -> PhenotypeT:
        pass

    @abstractmethod
    def to_dict(self) -> dict[str, Any]:
        pass

    @classmethod
    @abstractmethod
    def from_dict(cls, data: dict[str, Any]) -> "Genome":
        pass

    @classmethod
    @abstractmethod
    def random(cls: type[GenomeT], shape: "NetworkShape", rng: np.random.Generator, mutation_scale: float) -> GenomeT:
        pass


@dataclass(frozen=True, slots=True)
class NetworkShape(ConfigBase):
    CONFIG_TYPE = "network_shape"
    input_size: int
    hidden_layers: tuple[int, ...]
    output_size: int
    activation: str = "tanh"
    output_activation: str = "sigmoid"

    @property
    def layer_sizes(self) -> tuple[int, ...]:
        return (self.input_size, *self.hidden_layers, self.output_size)

    @property
    def parameter_count(self) -> int:
        total = 0
        for i, o in zip(self.layer_sizes, self.layer_sizes[1:]):
            total += (i * o) + o
        return total


@dataclass(frozen=True, slots=True)
class MutationConfig(ConfigBase):
    CONFIG_TYPE = "mutation_config"
    mutation_probability: float = 0.18
    mutation_strength: float = 0.35
    mutation_scale_learning_rate: float = 0.12
    min_mutation_scale: float = 0.01
    max_mutation_scale: float = 3.0


class Phenotype(Protocol):
    def predict(self, inputs: np.ndarray) -> np.ndarray: ...
    def get_parameters(self) -> np.ndarray: ...
    def set_parameters(self, params: np.ndarray) -> None: ...