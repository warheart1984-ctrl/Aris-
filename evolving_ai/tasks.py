from __future__ import annotations

from dataclasses import dataclass
import math
from typing import Protocol

from .config import NetworkShape
from .network import NeuralNetwork


@dataclass(frozen=True, slots=True)
class TaskEvaluation:
    objective_score: float
    behavior: tuple[float, ...]
    diagnostics: dict[str, float]


class EvolutionTask(Protocol):
    name: str
    shape: NetworkShape

    def evaluate(self, network: NeuralNetwork) -> TaskEvaluation:
        ...


@dataclass(frozen=True, slots=True)
class XorTask:
    hidden_layers: tuple[int, ...] = (6, 6)
    name: str = "xor"

    @property
    def shape(self) -> NetworkShape:
        return NetworkShape(
            input_size=2,
            hidden_layers=self.hidden_layers,
            output_size=1,
            activation="tanh",
            output_activation="sigmoid",
        )

    def evaluate(self, network: NeuralNetwork) -> TaskEvaluation:
        cases = (
            ((0.0, 0.0), 0.0),
            ((0.0, 1.0), 1.0),
            ((1.0, 0.0), 1.0),
            ((1.0, 1.0), 0.0),
        )
        predictions: list[float] = []
        squared_error = 0.0
        correct = 0

        for features, expected in cases:
            prediction = network.predict(features)[0]
            predictions.append(prediction)
            squared_error += (prediction - expected) ** 2
            if int(prediction >= 0.5) == int(expected):
                correct += 1

        mse = squared_error / len(cases)
        accuracy = correct / len(cases)
        objective = max(0.0, 0.65 * accuracy + 0.35 * (1.0 / (1.0 + mse)))

        return TaskEvaluation(
            objective_score=objective,
            behavior=tuple(predictions),
            diagnostics={"mse": mse, "accuracy": accuracy},
        )


@dataclass(frozen=True, slots=True)
class SequencePredictionTask:
    window_size: int = 5
    hidden_layers: tuple[int, ...] = (12, 8)
    train_points: int = 48
    holdout_points: int = 12
    name: str = "sequence"

    @property
    def shape(self) -> NetworkShape:
        return NetworkShape(
            input_size=self.window_size,
            hidden_layers=self.hidden_layers,
            output_size=1,
            activation="tanh",
            output_activation="sigmoid",
        )

    def _series(self, count: int) -> tuple[float, ...]:
        values: list[float] = []
        for index in range(count + self.window_size + 1):
            raw = (
                0.55
                + 0.25 * math.sin(index * 0.31)
                + 0.15 * math.sin(index * 0.07 + 1.3)
                + 0.05 * math.cos(index * 0.17)
            )
            values.append(max(0.0, min(1.0, raw)))
        return tuple(values)

    def _windows(self) -> tuple[list[tuple[float, ...]], list[float]]:
        series = self._series(self.train_points + self.holdout_points)
        inputs: list[tuple[float, ...]] = []
        outputs: list[float] = []
        for index in range(self.train_points + self.holdout_points):
            inputs.append(series[index : index + self.window_size])
            outputs.append(series[index + self.window_size])
        return inputs, outputs

    def evaluate(self, network: NeuralNetwork) -> TaskEvaluation:
        inputs, expected = self._windows()
        predictions: list[float] = []
        train_error = 0.0
        holdout_error = 0.0

        for index, (window, target) in enumerate(zip(inputs, expected)):
            prediction = network.predict(window)[0]
            predictions.append(prediction)
            if index < self.train_points:
                train_error += (prediction - target) ** 2
            else:
                holdout_error += (prediction - target) ** 2

        train_mse = train_error / self.train_points
        holdout_mse = holdout_error / self.holdout_points
        objective = max(0.0, 1.0 - ((train_mse * 0.8) + (holdout_mse * 0.2)))
        behavior = tuple(predictions[self.train_points : self.train_points + 8])

        return TaskEvaluation(
            objective_score=objective,
            behavior=behavior,
            diagnostics={"train_mse": train_mse, "holdout_mse": holdout_mse},
        )
