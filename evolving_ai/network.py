from __future__ import annotations

from dataclasses import dataclass
import math
from typing import Sequence

from .config import ActivationName, NetworkShape
from .genome import Genome


def _activate(kind: ActivationName, value: float) -> float:
    if kind == "relu":
        return max(0.0, value)
    if kind == "sigmoid":
        return 1.0 / (1.0 + math.exp(-value))
    if kind == "tanh":
        return math.tanh(value)
    raise ValueError(f"Unsupported activation: {kind}")


@dataclass(frozen=True, slots=True)
class LayerParameters:
    weights: tuple[tuple[float, ...], ...]
    biases: tuple[float, ...]


@dataclass(frozen=True, slots=True)
class NeuralNetwork:
    shape: NetworkShape
    layers: tuple[LayerParameters, ...]

    @classmethod
    def from_genome(cls, shape: NetworkShape, genome: Genome) -> "NeuralNetwork":
        values = genome.genes
        layers: list[LayerParameters] = []
        cursor = 0

        for input_width, output_width in zip(shape.layer_sizes, shape.layer_sizes[1:]):
            layer_weights: list[tuple[float, ...]] = []
            biases: list[float] = []
            for _ in range(output_width):
                next_cursor = cursor + input_width
                neuron_weights = values[cursor:next_cursor]
                if len(neuron_weights) != input_width:
                    raise ValueError("Genome does not have enough parameters to decode.")
                cursor = next_cursor
                layer_weights.append(tuple(neuron_weights))
                biases.append(values[cursor])
                cursor += 1
            layers.append(
                LayerParameters(weights=tuple(layer_weights), biases=tuple(biases))
            )

        if cursor != len(values):
            raise ValueError("Genome contained extra unused parameters.")

        return cls(shape=shape, layers=tuple(layers))

    def predict(self, inputs: Sequence[float]) -> tuple[float, ...]:
        if len(inputs) != self.shape.input_size:
            raise ValueError(
                f"Expected {self.shape.input_size} inputs, got {len(inputs)}."
            )

        current = list(float(value) for value in inputs)
        final_index = len(self.layers) - 1

        for layer_index, layer in enumerate(self.layers):
            activation = (
                self.shape.output_activation
                if layer_index == final_index
                else self.shape.activation
            )
            next_values: list[float] = []
            for neuron_weights, bias in zip(layer.weights, layer.biases):
                weighted_sum = sum(
                    weight * signal for weight, signal in zip(neuron_weights, current)
                ) + bias
                next_values.append(_activate(activation, weighted_sum))
            current = next_values

        return tuple(current)
