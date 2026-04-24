from __future__ import annotations

from dataclasses import dataclass
import math
import random

from .config import EvolutionConfig, NetworkShape


def _clamp(value: float, minimum: float, maximum: float) -> float:
    return max(minimum, min(maximum, value))


@dataclass(frozen=True, slots=True)
class Genome:
    genes: tuple[float, ...]
    mutation_scale: float
    lineage_depth: int = 0
    age: int = 0

    @classmethod
    def random(
        cls,
        shape: NetworkShape,
        rng: random.Random,
        mutation_scale: float,
    ) -> "Genome":
        spread = 1.0 / math.sqrt(shape.input_size)
        genes = tuple(rng.gauss(0.0, spread) for _ in range(shape.parameter_count))
        return cls(genes=genes, mutation_scale=mutation_scale)

    def with_age(self, age: int) -> "Genome":
        return Genome(
            genes=self.genes,
            mutation_scale=self.mutation_scale,
            lineage_depth=self.lineage_depth,
            age=age,
        )

    def crossover(self, other: "Genome", rng: random.Random) -> "Genome":
        if len(self.genes) != len(other.genes):
            raise ValueError("Both parents must have the same genome size.")

        child_genes: list[float] = []
        for left_gene, right_gene in zip(self.genes, other.genes):
            if rng.random() < 0.5:
                child_genes.append(left_gene)
            else:
                child_genes.append((left_gene + right_gene) / 2.0)

        return Genome(
            genes=tuple(child_genes),
            mutation_scale=(self.mutation_scale + other.mutation_scale) / 2.0,
            lineage_depth=max(self.lineage_depth, other.lineage_depth) + 1,
            age=0,
        )

    def mutate(self, config: EvolutionConfig, rng: random.Random) -> "Genome":
        next_scale = _clamp(
            self.mutation_scale
            * math.exp(rng.gauss(0.0, config.mutation_scale_learning_rate)),
            0.01,
            3.0,
        )
        next_genes = list(self.genes)
        mutated_any = False

        for index, current in enumerate(next_genes):
            if rng.random() <= config.mutation_probability:
                next_genes[index] = current + rng.gauss(0.0, next_scale)
                mutated_any = True

        if not mutated_any:
            forced_index = rng.randrange(len(next_genes))
            next_genes[forced_index] += rng.gauss(0.0, next_scale)

        return Genome(
            genes=tuple(next_genes),
            mutation_scale=next_scale,
            lineage_depth=self.lineage_depth + 1,
            age=0,
        )

    def distance(self, other: "Genome") -> float:
        if len(self.genes) != len(other.genes):
            raise ValueError("Genome distance requires equal-length vectors.")
        squared = [(left - right) ** 2 for left, right in zip(self.genes, other.genes)]
        return math.sqrt(sum(squared))

    def to_dict(self) -> dict[str, object]:
        return {
            "genes": list(self.genes),
            "mutation_scale": self.mutation_scale,
            "lineage_depth": self.lineage_depth,
            "age": self.age,
        }
