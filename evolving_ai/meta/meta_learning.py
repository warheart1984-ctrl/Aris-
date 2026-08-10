from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any, Callable, Dict, List, Tuple, TypeVar
import copy
import random

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


@dataclass
class MetaGenome(Genome):
    """Genome that encodes hyperparameters, architecture, or learning rules."""
    params: Dict[str, Any] = field(default_factory=dict)
    param_types: Dict[str, str] = field(default_factory=dict)  # "float", "int", "choice", "bool"
    mutation_scale: float = 0.1
    lineage_depth: int = 0
    age: int = 0

    def mutate(self, config: Any, rng: random.Random) -> "MetaGenome":
        new_params = {}
        for key, value in self.params.items():
            ptype = self.param_types.get(key, "float")
            if ptype == "float":
                new_params[key] = value + rng.gauss(0.0, self.mutation_scale)
            elif ptype == "int":
                new_params[key] = max(1, int(value + rng.gauss(0.0, max(1, self.mutation_scale))))
            elif ptype == "choice":
                choices = self.params.get(f"_choices_{key}", [value])
                if rng.random() < 0.1:
                    new_params[key] = rng.choice(choices)
                else:
                    new_params[key] = value
            elif ptype == "bool":
                new_params[key] = not value if rng.random() < 0.05 else value
            else:
                new_params[key] = value

        new_params["_choices_"] = self.params.get("_choices_", {})

        return MetaGenome(
            params=new_params,
            param_types=self.param_types.copy(),
            mutation_scale=max(0.01, min(1.0, self.mutation_scale * math.exp(rng.gauss(0.0, 0.1)))),
            lineage_depth=self.lineage_depth + 1,
            age=0,
        )

    def crossover(self, other: "MetaGenome", rng: random.Random) -> "MetaGenome":
        new_params = {}
        all_keys = set(self.params.keys()) | set(other.params.keys())
        for key in all_keys:
            if key.startswith("_"):
                continue
            if key in self.params and key in other.params:
                new_params[key] = self.params[key] if rng.random() < 0.5 else other.params[key]
            elif key in self.params:
                new_params[key] = self.params[key]
            else:
                new_params[key] = other.params[key]

        # Merge choices
        choices = {}
        for k, v in self.params.items():
            if k.startswith("_choices_"):
                choices[k] = v
        for k, v in other.params.items():
            if k.startswith("_choices_"):
                choices[k] = v

        new_params.update(choices)

        return MetaGenome(
            params=new_params,
            param_types={**self.param_types, **other.param_types},
            mutation_scale=(self.mutation_scale + other.mutation_scale) / 2,
            lineage_depth=max(self.lineage_depth, other.lineage_depth) + 1,
            age=0,
        )

    def distance(self, other: "MetaGenome") -> float:
        all_keys = set(self.params.keys()) | set(other.params.keys())
        diff = 0.0
        for key in all_keys:
            if key.startswith("_"):
                continue
            v1 = self.params.get(key)
            v2 = other.params.get(key)
            if v1 is None or v2 is None:
                diff += 1.0
            elif isinstance(v1, (int, float)) and isinstance(v2, (int, float)):
                diff += abs(v1 - v2)
            elif v1 != v2:
                diff += 1.0
        return diff

    def to_dict(self) -> Dict[str, Any]:
        return {
            "type": "meta",
            "params": self.params,
            "param_types": self.param_types,
            "mutation_scale": self.mutation_scale,
            "lineage_depth": self.lineage_depth,
            "age": self.age,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "MetaGenome":
        return cls(
            params=data["params"],
            param_types=data["param_types"],
            mutation_scale=data["mutation_scale"],
            lineage_depth=data.get("lineage_depth", 0),
            age=data.get("age", 0),
        )

    @classmethod
    def random(cls, shape: Any, rng: random.Random, mutation_scale: float) -> "MetaGenome":
        return cls(mutation_scale=mutation_scale)


class MetaTask(Task):
    """Task that evaluates a meta-genome by running inner evolution."""

    def __init__(
        self,
        base_task: Task,
        inner_config: EvolutionConfig,
        inner_generations: int = 10,
        inner_population_size: int = 20,
        metric: str = "best_fitness",
    ) -> None:
        self.base_task = base_task
        self.inner_config = inner_config
        self.inner_generations = inner_generations
        self.inner_population_size = inner_population_size
        self.metric = metric
        self.name = f"meta_{base_task.name}"

    def evaluate(self, genome: MetaGenome) -> float:
        # Decode meta-genome into inner evolution config
        inner_config = self._decode_config(genome)

        # Run inner evolution
        from .core import EvolutionEngine, NoveltyArchive

        # Create initial population for inner loop
        inner_pop = [
            DenseGenome.random(100, 0.1, random.Random())
            for _ in range(self.inner_population_size)
        ]

        engine = EvolutionEngine(inner_config, self.base_task, NoveltyArchive())
        result = engine.run(inner_pop)

        if self.metric == "best_fitness":
            return result.best.fitness
        elif self.metric == "final_avg_fitness":
            return result.history[-1].avg_fitness if result.history else 0.0
        elif self.metric == "improvement":
            if len(result.history) >= 2:
                return result.history[-1].avg_fitness - result.history[0].avg_fitness
            return 0.0
        else:
            return result.best.fitness

    def _decode_config(self, genome: MetaGenome) -> EvolutionConfig:
        config = EvolutionConfig()
        for key, value in genome.params.items():
            if key.startswith("_"):
                continue
            if hasattr(config, key):
                setattr(config, key, value)
        return config

    def behavior_descriptor(self, genome: MetaGenome) -> Tuple[float, ...]:
        # Behavior = inner evolution trajectory summary
        inner_config = self._decode_config(genome)
        inner_pop = [
            DenseGenome.random(100, 0.1, random.Random())
            for _ in range(self.inner_population_size)
        ]
        from .core import EvolutionEngine, NoveltyArchive
        engine = EvolutionEngine(inner_config, self.base_task, NoveltyArchive())
        result = engine.run(inner_pop)

        # Return trajectory as behavior
        traj = [h.avg_fitness for h in result.history]
        if len(traj) < 5:
            traj = traj + [traj[-1]] * (5 - len(traj))
        return tuple(traj[:5])


class OptimizerMetaGenome(MetaGenome):
    """Genome encoding an optimizer (learning rate schedule, momentum, etc.)."""

    @classmethod
    def create_optimizer_space(cls) -> "OptimizerMetaGenome":
        return cls(
            params={
                "learning_rate": 0.001,
                "momentum": 0.9,
                "weight_decay": 1e-4,
                "lr_schedule": "cosine",
                "warmup_epochs": 5,
                "_choices_lr_schedule": ["constant", "cosine", "step", "exponential"],
            },
            param_types={
                "learning_rate": "float",
                "momentum": "float",
                "weight_decay": "float",
                "lr_schedule": "choice",
                "warmup_epochs": "int",
            },
            mutation_scale=0.1,
        )


class LossFunctionGenome(MetaGenome):
    """Genome encoding a loss function composition."""

    @classmethod
    def create_loss_space(cls) -> "LossFunctionGenome":
        return cls(
            params={
                "base_loss": "mse",
                "aux_losses": "none",
                "loss_weights": "1.0",
                "label_smoothing": 0.0,
                "focal_gamma": 2.0,
                "_choices_base_loss": ["mse", "mae", "huber", "cross_entropy", "focal"],
                "_choices_aux_losses": ["none", "kl", "contrastive", "regularization"],
            },
            param_types={
                "base_loss": "choice",
                "aux_losses": "choice",
                "loss_weights": "float",
                "label_smoothing": "float",
                "focal_gamma": "float",
            },
            mutation_scale=0.1,
        )


class ActivationGenome(MetaGenome):
    """Genome encoding activation functions."""

    @classmethod
    def create_activation_space(cls) -> "ActivationGenome":
        return cls(
            params={
                "hidden_activation": "relu",
                "output_activation": "sigmoid",
                "hidden_alpha": 0.01,  # for leaky relu, elu, etc.
                "_choices_hidden_activation": ["relu", "leaky_relu", "elu", "selu", "gelu", "swish", "tanh", "sigmoid"],
                "_choices_output_activation": ["sigmoid", "softmax", "linear", "tanh"],
            },
            param_types={
                "hidden_activation": "choice",
                "output_activation": "choice",
                "hidden_alpha": "float",
            },
            mutation_scale=0.1,
        )


class ArchitectureGenome(MetaGenome):
    """Genome encoding neural architecture (layers, connections, etc.)."""

    @classmethod
    def create_architecture_space(cls, max_layers: int = 6, max_width: int = 256) -> "ArchitectureGenome":
        num_layers = random.randint(1, max_layers)
        layers = []
        for i in range(num_layers):
            layers.append(random.randint(16, max_width))

        return cls(
            params={
                "num_layers": num_layers,
                "layer_widths": tuple(layers),
                "skip_connections": False,
                "normalization": "none",
                "dropout_rate": 0.0,
                "_choices_normalization": ["none", "batch_norm", "layer_norm", "group_norm"],
            },
            param_types={
                "num_layers": "int",
                "layer_widths": "choice",  # special handling
                "skip_connections": "bool",
                "normalization": "choice",
                "dropout_rate": "float",
            },
            mutation_scale=0.1,
        )


class MetaEvolutionEngine(EvolutionEngine):
    """Evolution engine for meta-learning (evolving evolution)."""

    def __init__(
        self,
        config: EvolutionConfig,
        meta_task: MetaTask,
        archive: Archive,
        rng: random.Random | None = None,
    ) -> None:
        super().__init__(config, meta_task, archive, rng)
        self.meta_task = meta_task

    def run(
        self,
        initial_population: List[MetaGenome],
        progress_callback: Callable[[GenerationSummary], None] | None = None,
    ) -> EvaluatedCandidate[MetaGenome]:
        # Override to use meta-genome evaluation
        population = initial_population
        best: EvaluatedCandidate[MetaGenome] | None = None

        for gen in range(self.config.generations):
            scored = []
            for genome in population:
                fitness = self.meta_task.evaluate(genome)
                descriptor = self.meta_task.behavior_descriptor(genome)
                novelty = self.archive.novelty(descriptor)
                blended = (1.0 - self.config.novelty_weight) * fitness + \
                          self.config.novelty_weight * novelty
                self.archive.add(descriptor, fitness, genome)
                scored.append(EvaluatedCandidate(
                    genome=genome,
                    fitness=fitness,
                    novelty=novelty,
                    score=blended,
                    descriptor=descriptor,
                ))

            scored.sort(key=lambda s: s.score, reverse=True)
            best = scored[0]
            population = self._next_generation(scored)

            if progress_callback:
                avg_fit = sum(s.fitness for s in scored) / len(scored)
                avg_nov = sum(s.novelty for s in scored) / len(scored)
                summary = GenerationSummary(
                    generation=gen,
                    best_fitness=best.fitness,
                    best_score=best.score,
                    avg_fitness=avg_fit,
                    avg_novelty=avg_nov,
                    archive_size=len(self.archive.entries) if hasattr(self.archive, 'entries') else 0,
                )
                progress_callback(summary)

        if best is None:
            raise RuntimeError("Meta-evolution finished without candidates.")
        return best


class ContinualEvolutionEngine(EvolutionEngine):
    """Evolution that continues across multiple tasks without catastrophic forgetting."""

    def __init__(
        self,
        config: EvolutionConfig,
        tasks: List[Task],
        archive: Archive,
        replay_buffer_size: int = 100,
        ewc_lambda: float = 1000.0,
        rng: random.Random | None = None,
    ) -> None:
        super().__init__(config, tasks[0], archive, rng)
        self.tasks = tasks
        self.current_task_idx = 0
        self.replay_buffer: List[EvaluatedCandidate] = []
        self.replay_buffer_size = replay_buffer_size
        self.ewc_lambda = ewc_lambda
        self.task_importance: Dict[int, np.ndarray] = {}

    def _compute_fisher_importance(self, genome: Genome, task: Task) -> np.ndarray:
        """Compute Fisher information for EWC."""
        # Simplified: return parameter magnitudes as importance
        if hasattr(genome, 'weights'):
            return np.abs(np.array(genome.weights))
        return np.ones(100)

    def _ewc_loss(self, genome: Genome, task_idx: int) -> float:
        """Elastic Weight Consolidation loss."""
        if task_idx not in self.task_importance:
            return 0.0
        importance = self.task_importance[task_idx]
        if hasattr(genome, 'weights'):
            params = np.array(genome.weights)
            # Distance from old params (simplified)
            return float(np.sum(importance * params ** 2))
        return 0.0

    def run_continual(
        self,
        initial_population: List[Genome],
        progress_callback: Callable[[GenerationSummary], None] | None = None,
    ) -> Dict[int, EvaluatedCandidate]:
        """Run evolution on each task sequentially."""
        results = {}
        population = initial_population

        for task_idx, task in enumerate(self.tasks):
            self.current_task_idx = task_idx
            self.task = task

            # Add replay from previous tasks
            if self.replay_buffer:
                replay_pop = [c.genome for c in self.replay_buffer[-self.replay_buffer_size:]]
                population = population[:len(population)//2] + replay_pop[:len(population)//2]

            # Run on current task
            result = self.run(population, progress_callback)

            # Store importance for EWC
            if result.best.genome:
                self.task_importance[task_idx] = self._compute_fisher_importance(result.best.genome, task)

            # Add to replay buffer
            self.replay_buffer.append(result.best)
            if len(self.replay_buffer) > self.replay_buffer_size:
                self.replay_buffer.pop(0)

            results[task_idx] = result
            population = [result.best.genome] * self.config.population_size  # Reset from best

        return results


class EvolutionaryDistillationEngine:
    """Distill ensemble/hall-of-fame into a single compact model."""

    def __init__(
        self,
        teacher_genomes: List[Genome],
        student_config: EvolutionConfig,
        student_task: Task,
        archive: Archive,
        rng: random.Random | None = None,
    ) -> None:
        self.teacher_genomes = teacher_genomes
        self.student_config = student_config
        self.student_task = student_task
        self.archive = archive
        self.rng = rng or random.Random()

    def distill(
        self,
        initial_student_pop: List[Genome],
        distillation_steps: int = 50,
        progress_callback: Callable[[GenerationSummary], None] | None = None,
    ) -> EvaluatedCandidate:
        """Train student to match teacher ensemble predictions."""
        from .core import EvolutionEngine

        class DistillationTask(Task):
            name = "distillation"

            def __init__(self, teachers: List[Genome], base_task: Task):
                self.teachers = teachers
                self.base_task = base_task

            def evaluate(self, genome: Genome) -> float:
                # Match teacher predictions on base task inputs
                total_error = 0.0
                num_samples = 20

                for _ in range(num_samples):
                    # Generate random input
                    if hasattr(self.base_task, 'input_size'):
                        x = np.random.randn(self.base_task.input_size)
                    else:
                        x = np.random.randn(10)

                    teacher_preds = []
                    for t in self.teachers:
                        if hasattr(t, 'to_phenotype'):
                            teacher_preds.append(t.to_phenotype().predict(x))
                        elif hasattr(t, 'evaluate'):
                            teacher_preds.append(t.evaluate(x))

                    if teacher_preds:
                        ensemble_pred = np.mean(teacher_preds, axis=0)
                        if hasattr(genome, 'to_phenotype'):
                            student_pred = genome.to_phenotype().predict(x)
                        else:
                            student_pred = np.zeros_like(ensemble_pred)
                        total_error += np.mean((student_pred - ensemble_pred) ** 2)

                return max(0.0, 1.0 - total_error / num_samples)

            def behavior_descriptor(self, genome: Genome) -> Tuple[float, ...]:
                return tuple()

        distill_task = DistillationTask(self.teacher_genomes, self.student_task)
        engine = EvolutionEngine(self.student_config, distill_task, self.archive, self.rng)
        return engine.run(initial_student_pop, progress_callback)


import math