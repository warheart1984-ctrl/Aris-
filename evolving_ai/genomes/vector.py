from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any
import numpy as np

from . import Genome, NetworkShape, MutationConfig, Phenotype


class NeuralNetwork:
    def __init__(self, shape: NetworkShape, weights: np.ndarray, biases: list[np.ndarray]) -> None:
        self.shape = shape
        self.weights = weights
        self.biases = biases
        self._activations = self._get_activations()

    def _get_activations(self) -> list[callable]:
        acts = []
        for _ in self.shape.hidden_layers:
            acts.append(self._get_activation(self.shape.activation))
        acts.append(self._get_activation(self.shape.output_activation))
        return acts

    @staticmethod
    def _get_activation(name: str) -> callable:
        if name == "relu":
            return lambda x: np.maximum(0, x)
        elif name == "sigmoid":
            return lambda x: 1 / (1 + np.exp(-np.clip(x, -500, 500)))
        elif name == "tanh":
            return np.tanh
        else:
            raise ValueError(f"Unknown activation: {name}")

    @classmethod
    def from_genome(cls, shape: NetworkShape, genome: "VectorGenome") -> "NeuralNetwork":
        params = genome.genes
        weights = []
        biases = []
        idx = 0
        for i, o in zip(shape.layer_sizes, shape.layer_sizes[1:]):
            w = params[idx:idx + i * o].reshape(o, i)
            weights.append(w)
            idx += i * o
            b = params[idx:idx + o]
            biases.append(b)
            idx += o
        return cls(shape, np.concatenate(weights), biases)

    def predict(self, inputs: np.ndarray) -> np.ndarray:
        x = np.asarray(inputs, dtype=float).flatten()
        for w, b, act in zip(self.weights, self.biases, self._activations):
            x = act(w @ x + b)
        return x

    def get_parameters(self) -> np.ndarray:
        return np.concatenate([w.flatten() for w in self.weights] + self.biases)

    def set_parameters(self, params: np.ndarray) -> None:
        idx = 0
        new_weights = []
        new_biases = []
        for i, o in zip(self.shape.layer_sizes, self.shape.layer_sizes[1:]):
            w = params[idx:idx + i * o].reshape(o, i)
            new_weights.append(w)
            idx += i * o
            b = params[idx:idx + o]
            new_biases.append(b)
            idx += o
        self.weights = np.concatenate(new_weights)
        self.biases = new_biases


@dataclass(frozen=True, slots=True)
class VectorGenome(Genome[NeuralNetwork]):
    genes: tuple[float, ...]
    mutation_scale: float
    lineage_depth: int = 0
    age: int = 0

    @classmethod
    def random(cls, shape: NetworkShape, rng: np.random.Generator, mutation_scale: float) -> "VectorGenome":
        spread = 1.0 / np.sqrt(shape.input_size)
        genes = tuple(rng.normal(0.0, spread, shape.parameter_count))
        return cls(genes=genes, mutation_scale=mutation_scale)

    def with_age(self, age: int) -> "VectorGenome":
        return VectorGenome(
            genes=self.genes,
            mutation_scale=self.mutation_scale,
            lineage_depth=self.lineage_depth,
            age=age,
        )

    def mutate(self, config: MutationConfig, rng: np.random.Generator) -> "VectorGenome":
        next_scale = np.clip(
            self.mutation_scale * np.exp(rng.normal(0.0, config.mutation_scale_learning_rate)),
            config.min_mutation_scale,
            config.max_mutation_scale,
        )
        next_genes = np.array(self.genes, copy=True)
        mutated_any = False

        for i in range(len(next_genes)):
            if rng.random() <= config.mutation_probability:
                next_genes[i] += rng.normal(0.0, next_scale)
                mutated_any = True

        if not mutated_any:
            idx = rng.integers(len(next_genes))
            next_genes[idx] += rng.normal(0.0, next_scale)

        return VectorGenome(
            genes=tuple(next_genes),
            mutation_scale=float(next_scale),
            lineage_depth=self.lineage_depth + 1,
            age=0,
        )

    def crossover(self, other: "VectorGenome", rng: np.random.Generator) -> "VectorGenome":
        if len(self.genes) != len(other.genes):
            raise ValueError("Both parents must have the same genome size.")

        child_genes = []
        for left_gene, right_gene in zip(self.genes, other.genes):
            if rng.random() < 0.5:
                child_genes.append(left_gene)
            else:
                child_genes.append((left_gene + right_gene) / 2.0)

        return VectorGenome(
            genes=tuple(child_genes),
            mutation_scale=(self.mutation_scale + other.mutation_scale) / 2.0,
            lineage_depth=max(self.lineage_depth, other.lineage_depth) + 1,
            age=0,
        )

    def distance(self, other: "VectorGenome") -> float:
        if len(self.genes) != len(other.genes):
            raise ValueError("Genome distance requires equal-length vectors.")
        diff = np.array(self.genes) - np.array(other.genes)
        return float(np.sqrt(np.sum(diff ** 2)))

    def to_phenotype(self) -> NeuralNetwork:
        from . import NetworkShape
        raise NotImplementedError("Use NeuralNetwork.from_genome(shape, self)")

    def to_dict(self) -> dict[str, Any]:
        return {
            "type": "vector",
            "genes": list(self.genes),
            "mutation_scale": self.mutation_scale,
            "lineage_depth": self.lineage_depth,
            "age": self.age,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "VectorGenome":
        return cls(
            genes=tuple(data["genes"]),
            mutation_scale=data["mutation_scale"],
            lineage_depth=data.get("lineage_depth", 0),
            age=data.get("age", 0),
        )