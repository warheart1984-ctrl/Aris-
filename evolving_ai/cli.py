from __future__ import annotations

import argparse
import json
import random
from pathlib import Path
from typing import Any

from .core import (
    EvolutionConfig,
    EvolutionRuntime,
    DenseGenome,
    XorTask,
    SequencePredictionTask,
    NoveltyArchive,
    GenerationSummary,
    create_task,
)

from .engines.advanced import (
    SpeciationEngine,
    MapElitesEngine,
    NSGA2Engine,
    CMAESEngine,
)


def _parse_hidden_layers(
    value: list[int] | None, defaults: tuple[int, ...]
) -> tuple[int, ...]:
    if not value:
        return defaults
    if any(size <= 0 for size in value):
        raise argparse.ArgumentTypeError("Hidden layer sizes must be positive integers.")
    return tuple(value)


def _print_progress(summary: GenerationSummary) -> None:
    print(
        f"gen={summary.generation:03d} "
        f"best_fit={summary.best_fitness:.4f} "
        f"best_score={summary.best_score:.4f} "
        f"avg_fit={summary.avg_fitness:.4f} "
        f"avg_nov={summary.avg_novelty:.4f} "
        f"archive={summary.archive_size}"
    )


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Run an evolving AI experiment.")
    parser.add_argument(
        "--engine",
        choices=("standard", "speciation", "map_elites", "nsga2", "cmaes"),
        default="standard",
        help="Which evolution engine to use.",
    )
    parser.add_argument(
        "--task",
        choices=("xor", "sequence"),
        default="xor",
        help="Which built-in task to evolve against.",
    )
    parser.add_argument(
        "--population",
        type=int,
        default=96,
        help="Population size per generation.",
    )
    parser.add_argument(
        "--generations",
        type=int,
        default=80,
        help="How many generations to evolve.",
    )
    parser.add_argument(
        "--hidden",
        nargs="*",
        type=int,
        help="Hidden layer sizes, for example: --hidden 16 12 8",
    )
    parser.add_argument("--seed", type=int, default=42, help="Random seed.")
    parser.add_argument(
        "--novelty-weight",
        type=float,
        default=0.25,
        help="Blend factor between objective fitness and novelty.",
    )
    parser.add_argument(
        "--mutation-rate",
        type=float,
        default=0.18,
        help="Probability of mutation per offspring.",
    )
    parser.add_argument(
        "--elite-fraction",
        type=float,
        default=0.05,
        help="Fraction of population to keep as elites.",
    )
    parser.add_argument(
        "--tournament-size",
        type=int,
        default=4,
        help="Tournament size for selection.",
    )
    parser.add_argument(
        "--archive-k",
        type=int,
        default=15,
        help="Number of neighbors for novelty calculation.",
    )
    parser.add_argument(
        "--genome-size",
        type=int,
        default=None,
        help="Genome size (auto-calculated from task if not provided).",
    )
    parser.add_argument(
        "--mutation-scale",
        type=float,
        default=0.1,
        help="Initial mutation scale.",
    )
    parser.add_argument(
        "--json-out",
        type=Path,
        help="Optional path to save the full experiment report as JSON.",
    )
    parser.add_argument(
        "--config",
        type=Path,
        help="Path to YAML/JSON config file.",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)

    rng = random.Random(args.seed)

    # Load config from file if provided
    if args.config:
        from .core import ExperimentConfig
        exp_config = ExperimentConfig.from_yaml(args.config) if args.config.suffix in (".yaml", ".yml") else ExperimentConfig.from_json(args.config)
        # Override with CLI args
        if args.population != 96:
            exp_config.evolution.population_size = args.population
        if args.generations != 80:
            exp_config.evolution.generations = args.generations
        config = exp_config.evolution
        task = create_task(exp_config.task.name, exp_config.task.hidden_layers)
        archive = NoveltyArchive(k=exp_config.archive.k)
    else:
        hidden_layers = _parse_hidden_layers(args.hidden, (6, 6) if args.task == "xor" else (12, 8))
        task = create_task(args.task, hidden_layers)

        config = EvolutionConfig(
            population_size=args.population,
            generations=args.generations,
            mutation_rate=args.mutation_rate,
            novelty_weight=args.novelty_weight,
            elite_fraction=args.elite_fraction,
            tournament_size=args.tournament_size,
            seed=args.seed,
        )
        archive = NoveltyArchive(k=args.archive_k)

    # Determine genome size from task
    if args.genome_size is not None:
        genome_size = args.genome_size
    else:
        # Calculate from task architecture
        layer_sizes = (task.input_size, *task.hidden_layers, task.output_size)
        genome_size = sum((i * o) + o for i, o in zip(layer_sizes, layer_sizes[1:]))

    # Create initial population
    population = [
        DenseGenome.random(genome_size, args.mutation_scale, rng)
        for _ in range(config.population_size)
    ]

    # Create and run the selected engine
    if args.engine == "standard":
        runtime = EvolutionRuntime.from_task(task, population, config)
        best = runtime.run(population, progress_callback=_print_progress)
    elif args.engine == "speciation":
        from .engines.advanced import SpeciationEngine
        engine = SpeciationEngine(config=config, task=task, archive=archive)
        best = engine.run(population, progress_callback=_print_progress)
    elif args.engine == "map_elites":
        from .engines.advanced import MapElitesEngine
        engine = MapElitesEngine(config=config, task=task, archive=archive)
        best = engine.run(population, progress_callback=_print_progress)
    elif args.engine == "nsga2":
        from .engines.advanced import NSGA2Engine
        engine = NSGA2Engine(config=config, task=task, archive=archive)
        best = engine.run(population, progress_callback=_print_progress)
    elif args.engine == "cmaes":
        from .engines.advanced import CMAESEngine
        engine = CMAESEngine(config=config, task=task, archive=archive)
        best = engine.run(population, progress_callback=_print_progress)
    else:
        raise ValueError(f"Unknown engine: {args.engine}")

    result = {
        "engine": args.engine,
        "lineage_id": best.genome.lineage_id,
        "fitness": best.fitness,
        "novelty": best.novelty,
        "score": best.score,
        "descriptor": best.descriptor,
    }

    if args.json_out:
        with open(args.json_out, "w", encoding="utf-8") as f:
            json.dump(result, f, indent=2)
        print(f"saved report to {args.json_out}")
    else:
        print(json.dumps(result, indent=2))

    return 0


if __name__ == "__main__":
    raise SystemExit(main())