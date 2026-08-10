from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any, Callable, Dict, List, Optional, Tuple
import time
import uuid
from concurrent.futures import ThreadPoolExecutor, ProcessPoolExecutor, as_completed

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


class DistributedBackend(ABC):
    @abstractmethod
    def map(self, fn: Callable, items: List[Any]) -> List[Any]:
        pass

    @abstractmethod
    def shutdown(self) -> None:
        pass


class ThreadPoolBackend(DistributedBackend):
    def __init__(self, max_workers: int = 4):
        self.executor = ThreadPoolExecutor(max_workers=max_workers)

    def map(self, fn: Callable, items: List[Any]) -> List[Any]:
        futures = [self.executor.submit(fn, item) for item in items]
        return [f.result() for f in as_completed(futures)]

    def shutdown(self) -> None:
        self.executor.shutdown(wait=True)


class ProcessPoolBackend(DistributedBackend):
    def __init__(self, max_workers: int = 4):
        self.executor = ProcessPoolExecutor(max_workers=max_workers)

    def map(self, fn: Callable, items: List[Any]) -> List[Any]:
        futures = [self.executor.submit(fn, item) for item in items]
        return [f.result() for f in as_completed(futures)]

    def shutdown(self) -> None:
        self.executor.shutdown(wait=True)


try:
    import ray

    class RayBackend(DistributedBackend):
        def __init__(self, num_cpus: int = 4, **ray_kwargs):
            if not ray.is_initialized():
                ray.init(num_cpus=num_cpus, **ray_kwargs)
            self._remote_fn = None

        def _make_remote(self, fn: Callable):
            @ray.remote
            def remote_fn(item):
                return fn(item)
            return remote_fn

        def map(self, fn: Callable, items: List[Any]) -> List[Any]:
            remote_fn = self._make_remote(fn)
            futures = [remote_fn.remote(item) for item in items]
            return ray.get(futures)

        def shutdown(self) -> None:
            ray.shutdown()

except ImportError:
    class RayBackend(DistributedBackend):
        def __init__(self, *args, **kwargs):
            raise ImportError("Ray not installed. Install with: pip install ray")

        def map(self, fn: Callable, items: List[Any]) -> List[Any]:
            raise NotImplementedError

        def shutdown(self) -> None:
            pass


try:
    from dask.distributed import Client, LocalCluster

    class DaskBackend(DistributedBackend):
        def __init__(self, n_workers: int = 4, threads_per_worker: int = 1, **kwargs):
            self.cluster = LocalCluster(n_workers=n_workers, threads_per_worker=threads_per_worker, **kwargs)
            self.client = Client(self.cluster)

        def map(self, fn: Callable, items: List[Any]) -> List[Any]:
            futures = self.client.map(fn, items)
            return self.client.gather(futures)

        def shutdown(self) -> None:
            self.client.close()
            self.cluster.close()

except ImportError:
    class DaskBackend(DistributedBackend):
        def __init__(self, *args, **kwargs):
            raise ImportError("Dask not installed. Install with: pip install dask distributed")

        def map(self, fn: Callable, items: List[Any]) -> List[Any]:
            raise NotImplementedError

        def shutdown(self) -> None:
            pass


try:
    import ray
    from ray.util.dask import ray_dask_get, enable_dask_on_ray
    import dask
    import dask.distributed
    from dask.distributed import Client, LocalCluster

    class DaskOnRayBackend(DistributedBackend):
        """Dask with Ray scheduler (dask-on-ray) for distributed evaluation."""
        
        def __init__(self, n_workers: int = 4, threads_per_worker: int = 1, **ray_kwargs):
            # Initialize Ray if not already initialized
            if not ray.is_initialized():
                ray.init(**ray_kwargs)
            
            # Create a local Dask cluster that will use Ray as scheduler
            self.cluster = LocalCluster(
                n_workers=n_workers,
                threads_per_worker=threads_per_worker,
                processes=True,
                scheduler_port=0,
                silence_logs=False
            )
            self.client = Client(self.cluster)
            
            # Enable Dask-on-Ray scheduler globally
            enable_dask_on_ray()
            
            # Store the original scheduler for reference
            self._scheduler = ray_dask_get

        def map(self, fn: Callable, items: List[Any]) -> List[Any]:
            """Map function over items using Dask with Ray scheduler."""
            # Use the Dask client to map the function
            # The Dask-on-Ray scheduler will execute tasks on Ray workers
            futures = self.client.map(fn, items)
            return self.client.gather(futures)

        def shutdown(self) -> None:
            try:
                self.client.close()
            except Exception:
                pass
            try:
                self.cluster.close()
            except Exception:
                pass

except ImportError:
    class DaskOnRayBackend(DistributedBackend):
        def __init__(self, *args, **kwargs):
            raise ImportError("Ray or Dask not installed. Install with: pip install ray dask distributed")

        def map(self, fn: Callable, items: List[Any]) -> List[Any]:
            raise NotImplementedError

        def shutdown(self) -> None:
            pass


@dataclass
class DistributedEvolutionConfig(EvolutionConfig):
    backend: str = "thread"  # "thread", "process", "ray", "dask"
    num_workers: int = 4
    batch_size: int = 32
    eval_timeout: float = 300.0
    checkpoint_interval: int = 10
    checkpoint_dir: str = "./checkpoints"


class DistributedEvolutionEngine:
    """Evolution engine with distributed evaluation."""

    def __init__(
        self,
        config: DistributedEvolutionConfig,
        task: Task,
        archive: Archive,
        backend: Optional[DistributedBackend] = None,
        forge_eval: Any = None,
    ) -> None:
        self.config = config
        self.task = task
        self.archive = archive
        self._backend = backend or self._create_backend()
        self.rng = np.random.default_rng(config.seed)
        self.hall_of_fame: List[EvaluatedCandidate] = []
        self.history: List[GenerationSummary] = []
        self.best_fitness = -float('inf')
        self.stagnation = 0
        self.generation = 0
        self.forge_eval = forge_eval

    def __getstate__(self):
        """Return state for pickling, excluding the backend."""
        state = self.__dict__.copy()
        # Remove the backend as it contains unpicklable objects (Dask client, Ray handles)
        state.pop('_backend', None)
        state.pop('backend', None)
        return state

    def __setstate__(self, state):
        self.__dict__.update(state)
        # Recreate the backend on unpickling
        self._backend = self._create_backend()

    @property
    def backend(self) -> DistributedBackend:
        if not hasattr(self, '_backend') or self._backend is None:
            self._backend = self._create_backend()
        return self._backend

    @backend.setter
    def backend(self, value: DistributedBackend):
        self._backend = value

    def _create_backend(self) -> DistributedBackend:
        if self.config.backend == "thread":
            return ThreadPoolBackend(self.config.num_workers)
        elif self.config.backend == "process":
            return ProcessPoolBackend(self.config.num_workers)
        elif self.config.backend == "ray":
            return RayBackend(self.config.num_workers)
        elif self.config.backend == "dask":
            return DaskBackend(self.config.num_workers)
        elif self.config.backend == "dask_on_ray":
            return DaskOnRayBackend(self.config.num_workers)
        else:
            raise ValueError(f"Unknown backend: {self.config.backend}")

    def _evaluate_batch(self, genomes: List[Genome]) -> List[Tuple[Genome, float, Tuple[float, ...], Dict[str, float]]]:
        """Evaluate a batch of genomes in parallel."""
        def eval_one(genome: Genome):
            fitness = self.task.evaluate(genome)
            descriptor = self.task.behavior_descriptor(genome)
            diagnostics = {}
            return genome, fitness, descriptor, diagnostics

        return self.backend.map(eval_one, genomes)

    def _evaluate_population(self, population: List[Genome]) -> List[EvaluatedCandidate[Genome]]:
        """Evaluate entire population, split into batches."""
        # Split into batches
        batches = [
            population[i:i + self.config.batch_size]
            for i in range(0, len(population), self.config.batch_size)
        ]

        all_results = []
        for batch in batches:
            results = self._evaluate_batch(batch)
            all_results.extend(results)

        # Process results
        candidates = []
        for genome, fitness, descriptor, diagnostics in all_results:
            novelty = self.archive.novelty(descriptor)
            combined = (1.0 - self.config.novelty_weight) * fitness + \
                       self.config.novelty_weight * novelty
            self.archive.add(descriptor, fitness, genome)
            candidates.append(EvaluatedCandidate(
                genome=genome,
                fitness=fitness,
                novelty=novelty,
                score=combined,
                descriptor=descriptor,
            ))

        return sorted(candidates, key=lambda c: c.score, reverse=True)

    def _next_generation(self, scored: List[EvaluatedCandidate[Genome]]) -> List[Genome]:
        scored.sort(key=lambda c: c.score, reverse=True)
        n = len(scored)
        elite_count = max(1, int(self.config.elite_fraction * n))
        elites = [c.genome.clone() for c in scored[:elite_count]]

        def tournament() -> Genome:
            import random
            candidates = random.sample(scored, min(self.config.tournament_size, len(scored)))
            return max(candidates, key=lambda c: c.score).genome

        new_pop = elites[:]
        mut_config = self.config.to_mutation_config() if hasattr(self.config, 'to_mutation_config') else None

        while len(new_pop) < n:
            parent1 = tournament()
            parent2 = tournament()
            child = parent1.crossover(parent2, self.rng)
            if self.rng.random() < self.config.mutation_rate:
                if mut_config:
                    child = child.mutate(mut_config, self.rng)
                else:
                    child = child.mutate(self.rng)
            new_pop.append(child)

        return new_pop

    def run(
        self,
        initial_population: List[Genome],
        progress_callback: Callable[[GenerationSummary], None] | None = None,
    ) -> EvaluatedCandidate[Genome]:
        population = initial_population
        best: EvaluatedCandidate[Genome] | None = None

        for gen in range(self.config.generations):
            self.generation = gen
            scored = self._evaluate_population(population)
            best = scored[0]

            # Update hall of fame
            self.hall_of_fame.extend(scored[:self.config.elite_count])
            self.hall_of_fame.sort(key=lambda c: c.fitness, reverse=True)
            self.hall_of_fame = self.hall_of_fame[:self.config.hall_of_fame_size]

            # Checkpoint
            if gen % self.config.checkpoint_interval == 0:
                self._checkpoint(gen, scored)

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

        return best

    def _checkpoint(self, generation: int, scored: List[EvaluatedCandidate[Genome]]) -> None:
        import json
        from pathlib import Path
        Path(self.config.checkpoint_dir).mkdir(parents=True, exist_ok=True)
        checkpoint = {
            "generation": generation,
            "best": scored[0].genome.to_dict() if hasattr(scored[0].genome, 'to_dict') else {},
            "hall_of_fame": [c.genome.to_dict() for c in self.hall_of_fame],
            "config": self.config.to_dict() if hasattr(self.config, 'to_dict') else {},
        }
        path = Path(self.config.checkpoint_dir) / f"checkpoint_gen_{generation:04d}.json"
        path.write_text(json.dumps(checkpoint, indent=2))

    def shutdown(self) -> None:
        self.backend.shutdown()

    def _run_forge_eval(self, action: dict[str, Any]) -> list[dict[str, Any]]:
        """Run Forge evaluation on an action using the configured backend."""
        if self.forge_eval is None:
            return [
                {
                    "mode": "missing",
                    "passed": False,
                    "status_code": 503,
                    "reason": "Forge Eval is not connected.",
                    "raw": {},
                }
            ]

        results: list[dict[str, Any]] = []
        payload_text = action["patch"] or action["code"] or " ".join(action["command"])
        normalized_patch = action["patch"]
        if normalized_patch and "+++ b/" not in normalized_patch and action["target"]:
            target = action["target"].replace("\\", "/").strip()
            normalized_patch = f"--- a/{target}\n+++ b/{target}\n{normalized_patch.lstrip()}"

        def _failed_io_reason(base_reason: str, checks: list[dict[str, Any]]) -> str:
            failed_needles = [
                _text(item.get("needle"))
                for item in checks
                if not bool(item.get("passed")) and _text(item.get("needle"))
            ]
            if not failed_needles:
                return base_reason
            if len(failed_needles) == 1:
                return f"{base_reason} `{failed_needles[0]}` is not allowed."
            return f"{base_reason} Not allowed: {', '.join(f'`{needle}`' for needle in failed_needles)}."

        if action["patch"]:
            request_payload = {
                "task_id": action["action_id"],
                "mode": "repo_patch",
                "payload": {
                    "patch": normalized_patch,
                    "repo": str(self.repo_root),
                    "lineage": _text(action.get("lineage")),
                    "target": action["target"],
                    "diff_present": bool(action["patch"]),
                    "test_result": "not_run",
                    "config": {
                        "expected_files": [action["target"]] if action["target"] else [],
                    },
                },
            }
            response, status_code = self.forge_eval.evaluate(request_payload)
            raw = response.model_dump(exclude_none=True)
            details = raw.get("result", {}).get("details", {}) if status_code == 200 else {}
            touched_files = {
                _text(item).replace("\\", "/")
                for item in list(details.get("touched_files") or [])
                if _text(item)
            }
            expected_files = {
                _text(item).replace("\\", "/")
                for item in list(details.get("expected_files") or [])
                if _text(item)
            }
            passed = status_code == 200 and (
                not expected_files or bool(touched_files & expected_files)
            )
            results.append(
                {
                    "mode": "repo_patch",
                    "passed": passed,
                    "status_code": status_code,
                    "reason": (
                        "Forge Eval confirmed the patch scope."
                        if passed
                        else "Forge Eval rejected the patch scope."
                    ),
                    "raw": raw,
                }
            )
        if action["command"]:
            request_payload = {
                "task_id": action["action_id"],
                "mode": "io_tests",
                "payload": {
                    "program": " ".join(action["command"]),
                    "lineage": _text(action.get("lineage")),
                    "target": action["target"],
                    "diff_present": False,
                    "test_result": "not_run",
                    "config": {
                        "must_not_contain": self._dangerous_command_terms(),
                    },
                },
            }
            response, status_code = self.forge_eval.evaluate(request_payload)
            raw = response.model_dump(exclude_none=True)
            checks = list(raw.get("result", {}).get("details", {}).get("checks", []))
            passed = status_code == 200 and all(bool(item.get("passed")) for item in checks)
            results.append(
                {
                    "mode": "io_tests",
                    "passed": passed,
                    "status_code": status_code,
                    "reason": (
                        "Forge Eval cleared the command request."
                        if passed
                        else _failed_io_reason("Forge Eval rejected the command request.", checks)
                    ),
                    "raw": raw,
                }
            )
        if action["code"]:
            request_payload = {
                "task_id": action["action_id"],
                "mode": "io_tests",
                "payload": {
                    "program": action["code"],
                    "lineage": _text(action.get("lineage")),
                    "target": action["target"],
                    "diff_present": False,
                    "test_result": "not_run",
                    "config": {
                        "must_not_contain": [
                            "subprocess",
                            "socket",
                            "os.system",
                            "shutil.rmtree",
                            "eval(",
                            "exec(",
                        ],
                    },
                },
            }
            response, status_code = self.forge_eval.evaluate(request_payload)
            raw = response.model_dump(exclude_none=True)
            checks = list(raw.get("result", {}).get("details", {}).get("checks", []))
            passed = status_code == 200 and all(bool(item.get("passed")) for item in checks)
            results.append(
                {
                    "mode": "io_tests",
                    "passed": passed,
                    "status_code": status_code,
                    "reason": (
                        "Forge Eval cleared the Python execution request."
                        if passed
                        else _failed_io_reason("Forge Eval rejected the Python execution request.", checks)
                    ),
                    "raw": raw,
                }
            )
        if not results and payload_text:
            request_payload = {
                "task_id": action["action_id"],
                "mode": "llm_rubric",
                "payload": {
                    "program": payload_text,
                    "lineage": _text(action.get("lineage")),
                    "target": action["target"],
                    "diff_present": bool(action["patch"]),
                    "test_result": "not_run",
                    "config": {
                        "criteria": [
                            {
                                "label": "purpose-visible",
                                "required_terms": [action["purpose"].lower()] if action["purpose"] else [],
                            }
                        ]
                    },
                },
            }
            response, status_code = self.forge_eval.evaluate(request_payload)
            raw = response.model_dump(exclude_none=True)
            criteria = list(raw.get("result", {}).get("details", {}).get("criteria", []))
            passed = status_code == 200 and all(
                float(item.get("score", 0.0)) >= 1.0 for item in criteria
            )
            results.append(
                {
                    "mode": "llm_rubric",
                    "passed": passed,
                    "status_code": status_code,
                    "reason": (
                        "Forge Eval completed rubric verification."
                        if passed
                        else "Forge Eval rubric verification failed."
                    ),
                    "raw": raw,
                }
            )
        if not results:
            results.append(
                {
                    "mode": "noop",
                    "passed": False,
                    "status_code": 400,
                    "reason": "No evaluable Forge Eval artifact was provided.",
                    "raw": {},
                }
            )
        return results


class IslandModelEngine:
    """Island model with multiple subpopulations and migration."""

    def __init__(
        self,
        config: DistributedEvolutionConfig,
        task: Task,
        num_islands: int = 4,
        migration_interval: int = 10,
        migration_rate: float = 0.1,
        topology: str = "ring",
        backend: Optional[DistributedBackend] = None,
    ) -> None:
        self.config = config
        self.task = task
        self.num_islands = num_islands
        self.migration_interval = migration_interval
        self.migration_rate = migration_rate
        self.topology = topology
        self.backend = backend or ThreadPoolBackend(num_islands)

        # Create island engines
        self.islands = []
        for i in range(num_islands):
            island_config = DistributedEvolutionConfig(
                **{k: v for k, v in config.__dict__.items() if not k.startswith('_')},
                population_size=config.population_size // num_islands,
            )
            island = DistributedEvolutionEngine(
                island_config, task, NoveltyArchive(), backend=None  # Each island uses local eval
            )
            self.islands.append(island)

    def _migrate(self, generation: int) -> None:
        if generation % self.migration_interval != 0:
            return

        # Collect migrants from each island
        migrants = []
        for island in self.islands:
            if island.hall_of_fame:
                num_migrants = max(1, int(len(island.hall_of_fame) * self.migration_rate))
                migrants.append(island.hall_of_fame[:num_migrants])

        # Distribute based on topology
        if self.topology == "ring":
            for i, island in enumerate(self.islands):
                src_idx = (i - 1) % self.num_islands
                for migrant in migrants[src_idx]:
                    island.hall_of_fame.append(migrant)
                island.hall_of_fame.sort(key=lambda c: c.fitness, reverse=True)
                island.hall_of_fame = island.hall_of_fame[:island.config.hall_of_fame_size]
        elif self.topology == "fully_connected":
            all_migrants = [m for sublist in migrants for m in sublist]
            for island in self.islands:
                island.hall_of_fame.extend(all_migrants)
                island.hall_of_fame.sort(key=lambda c: c.fitness, reverse=True)
                island.hall_of_fame = island.hall_of_fame[:island.config.hall_of_fame_size]

    def run(
        self,
        initial_populations: List[List[Genome]],
        progress_callback: Callable[[int, List[GenerationSummary]], None] | None = None,
    ) -> List[EvaluatedCandidate[Genome]]:
        if len(initial_populations) != self.num_islands:
            raise ValueError(f"Expected {self.num_islands} initial populations")

        results = []

        for gen in range(self.config.generations):
            # Run one generation on each island in parallel
            def run_island(args):
                island, pop = args
                return island.run(pop)

            island_args = list(zip(self.islands, initial_populations))
            island_results = self.backend.map(run_island, island_args)

            # Migrate
            self._migrate(gen)

            # Prepare next populations
            initial_populations = [r.genome for r in island_results]  # Simplified

            # Progress
            if progress_callback:
                summaries = []
                for i, result in enumerate(island_results):
                    summaries.append(GenerationSummary(
                        generation=gen,
                        best_fitness=result.fitness,
                        best_score=result.score,
                        avg_fitness=result.fitness,  # Simplified
                        avg_novelty=result.novelty,
                        archive_size=len(self.islands[i].archive.entries) if hasattr(self.islands[i].archive, 'entries') else 0,
                    ))
                progress_callback(gen, summaries)

        # Return best from each island
        for island in self.islands:
            if island.hall_of_fame:
                results.append(island.hall_of_fame[0])

        self.shutdown()
        return results

    def shutdown(self) -> None:
        for island in self.islands:
            island.shutdown()
        self.backend.shutdown()


def create_distributed_engine(
    config: DistributedEvolutionConfig,
    task: Task,
    archive: Archive,
) -> DistributedEvolutionEngine:
    return DistributedEvolutionEngine(config, task, archive)


def create_island_engine(
    config: DistributedEvolutionConfig,
    task: Task,
    num_islands: int = 4,
    migration_interval: int = 10,
    migration_rate: float = 0.1,
    topology: str = "ring",
) -> IslandModelEngine:
    return IslandModelEngine(config, task, num_islands, migration_interval, migration_rate, topology)