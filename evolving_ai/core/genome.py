from __future__ import annotations

from dataclasses import dataclass
from typing import Any, List, Protocol
import uuid


class MutationConfig(Protocol):
    mutation_probability: float
    mutation_strength: float


class Genome(Protocol):
    def mutate(self, config: MutationConfig, rng: Any) -> "Genome":
        ...

    def crossover(self, other: "Genome", rng: Any) -> "Genome":
        ...

    def clone(self) -> "Genome":
        ...


@dataclass(frozen=True, slots=True)
class DenseGenome:
    weights: List[float]
    mutation_scale: float
    lineage_id: str
    age: int = 0

    def to_dict(self) -> dict[str, Any]:
        return {
            "weights": self.weights,
            "mutation_scale": self.mutation_scale,
            "lineage_id": self.lineage_id,
            "age": self.age,
        }

    def mutate(self, config: MutationConfig, rng: Any) -> "DenseGenome":
        new_weights = []
        # Support both Python's random.Random (gauss, randrange) and numpy's Generator (normal, integers)
        has_normal = hasattr(rng, 'normal')
        has_integers = hasattr(rng, 'integers')
        for w in self.weights:
            if rng.random() <= config.mutation_probability:
                delta = rng.normal(0.0, config.mutation_strength) if has_normal else rng.gauss(0.0, config.mutation_strength)
                new_weights.append(w + delta)
            else:
                new_weights.append(w)
        # Ensure at least one mutation
        if all(w == orig for w, orig in zip(new_weights, self.weights)):
            idx = rng.integers(len(new_weights)) if has_integers else rng.randrange(len(new_weights))
            delta = rng.normal(0.0, config.mutation_strength) if has_normal else rng.gauss(0.0, config.mutation_strength)
            new_weights[idx] += delta
        return DenseGenome(
            weights=new_weights,
            mutation_scale=self.mutation_scale,
            lineage_id=self.lineage_id,
            age=self.age + 1,
        )

    def crossover(self, other: "DenseGenome", rng: Any) -> "DenseGenome":
        assert len(self.weights) == len(other.weights)
        child = []
        for a, b in zip(self.weights, other.weights):
            child.append(a if rng.random() < 0.5 else b)
        return DenseGenome(
            weights=child,
            mutation_scale=(self.mutation_scale + other.mutation_scale) / 2.0,
            lineage_id=f"{self.lineage_id}+{other.lineage_id}",
            age=0,
        )

    def clone(self) -> "DenseGenome":
        return DenseGenome(
            weights=list(self.weights),
            mutation_scale=self.mutation_scale,
            lineage_id=self.lineage_id,
            age=self.age,
        )

    @classmethod
    def random(cls, size: int, mutation_scale: float, rng: Any) -> "DenseGenome":
        return cls(
            weights=[rng.uniform(-1.0, 1.0) for _ in range(size)],
            mutation_scale=mutation_scale,
            lineage_id=str(uuid.uuid4())[:8],
        )