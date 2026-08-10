from __future__ import annotations

from typing import Any, Dict, Protocol, Tuple
import numpy as np


class Task(Protocol):
    name: str

    def evaluate(self, genome: Any) -> float:
        ...

    def behavior_descriptor(self, genome: Any) -> Any:
        ...


class XorTask:
    name = "xor"

    def __init__(self, hidden_layers: Tuple[int, ...] = (6, 6)) -> None:
        self.hidden_layers = hidden_layers
        self.input_size = 2
        self.output_size = 1

    def evaluate(self, genome: Any) -> float:
        cases = (
            ((0.0, 0.0), 0.0),
            ((0.0, 1.0), 1.0),
            ((1.0, 0.0), 1.0),
            ((1.0, 1.0), 0.0),
        )
        predictions = []
        squared_error = 0.0
        correct = 0

        for features, expected in cases:
            prediction = self._predict(genome, features)[0]
            predictions.append(prediction)
            squared_error += (prediction - expected) ** 2
            if int(prediction >= 0.5) == int(expected):
                correct += 1

        mse = squared_error / len(cases)
        accuracy = correct / len(cases)
        objective = max(0.0, 0.65 * accuracy + 0.35 * (1.0 / (1.0 + mse)))
        return objective

    def behavior_descriptor(self, genome: Any) -> Tuple[float, ...]:
        cases = ((0.0, 0.0), (0.0, 1.0), (1.0, 0.0), (1.0, 1.0))
        return tuple(self._predict(genome, f)[0] for f in cases)

    def _predict(self, genome: DenseGenome, inputs: Tuple[float, ...]) -> np.ndarray:
        x = np.array(inputs, dtype=float)
        weights = genome.weights
        idx = 0
        layer_sizes = (self.input_size, *self.hidden_layers, self.output_size)

        for i, o in zip(layer_sizes, layer_sizes[1:]):
            w = np.array(weights[idx:idx + i * o]).reshape(o, i)
            idx += i * o
            b = np.array(weights[idx:idx + o])
            idx += o
            x = np.tanh(w @ x + b)
        x = 1 / (1 + np.exp(-np.clip(x, -500, 500)))
        return x


class SequencePredictionTask:
    name = "sequence"

    def __init__(
        self,
        window_size: int = 5,
        hidden_layers: Tuple[int, ...] = (12, 8),
        train_points: int = 48,
        holdout_points: int = 12,
    ) -> None:
        self.window_size = window_size
        self.hidden_layers = hidden_layers
        self.train_points = train_points
        self.holdout_points = holdout_points
        self.input_size = window_size
        self.output_size = 1

    def evaluate(self, genome: Any) -> float:
        inputs, expected = self._windows()
        predictions = []
        train_error = 0.0
        holdout_error = 0.0

        for index, (window, target) in enumerate(zip(inputs, expected)):
            prediction = self._predict(genome, window)[0]
            predictions.append(prediction)
            if index < self.train_points:
                train_error += (prediction - target) ** 2
            else:
                holdout_error += (prediction - target) ** 2

        train_mse = train_error / self.train_points
        holdout_mse = holdout_error / self.holdout_points
        objective = max(0.0, 1.0 - ((train_mse * 0.8) + (holdout_mse * 0.2)))
        return objective

    def behavior_descriptor(self, genome: Any) -> Tuple[float, ...]:
        inputs, _ = self._windows()
        holdout_inputs = inputs[self.train_points:self.train_points + 8]
        return tuple(self._predict(genome, w)[0] for w in holdout_inputs)

    def _series(self, count: int) -> Tuple[float, ...]:
        import math
        values = []
        for index in range(count + self.window_size + 1):
            raw = (
                0.55
                + 0.25 * math.sin(index * 0.31)
                + 0.15 * math.sin(index * 0.07 + 1.3)
                + 0.05 * math.cos(index * 0.17)
            )
            values.append(max(0.0, min(1.0, raw)))
        return tuple(values)

    def _windows(self) -> Tuple[Tuple[float, ...], Tuple[float, ...]]:
        series = self._series(self.train_points + self.holdout_points)
        inputs = []
        outputs = []
        for index in range(self.train_points + self.holdout_points):
            inputs.append(series[index:index + self.window_size])
            outputs.append(series[index + self.window_size])
        return tuple(inputs), tuple(outputs)

    def _predict(self, genome: DenseGenome, inputs: Tuple[float, ...]) -> np.ndarray:
        x = np.array(inputs, dtype=float)
        weights = genome.weights
        idx = 0
        layer_sizes = (self.input_size, *self.hidden_layers, self.output_size)

        for i, o in zip(layer_sizes, layer_sizes[1:]):
            w = np.array(weights[idx:idx + i * o]).reshape(o, i)
            idx += i * o
            b = np.array(weights[idx:idx + o])
            idx += o
            x = np.tanh(w @ x + b)
        x = 1 / (1 + np.exp(-np.clip(x, -500, 500)))
        return x


def create_task(name: str, hidden_layers: Tuple[int, ...] | None = None) -> Task:
    if name == "xor":
        return XorTask(hidden_layers=hidden_layers or (6, 6))
    if name == "sequence":
        return SequencePredictionTask(hidden_layers=hidden_layers or (12, 8))
    raise ValueError(f"Unknown task: {name}")