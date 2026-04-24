from __future__ import annotations

import argparse
from pathlib import Path

from .code_agents import CodeWritingBenchmarkTask
from .config import EvolutionConfig
from .engine import EvolutionEngine, GenerationSummary
from .network import NeuralNetwork
from .tasks import SequencePredictionTask, XorTask


def _parse_hidden_layers(
    value: list[int] | None, defaults: tuple[int, ...]
) -> tuple[int, ...]:
    if not value:
        return defaults
    if any(size <= 0 for size in value):
        raise argparse.ArgumentTypeError("Hidden layer sizes must be positive integers.")
    return tuple(value)


def _build_task(name: str, hidden_layers: tuple[int, ...]):
    if name == "code-agent":
        return CodeWritingBenchmarkTask(hidden_layers=hidden_layers)
    if name == "xor":
        return XorTask(hidden_layers=hidden_layers)
    if name == "sequence":
        return SequencePredictionTask(hidden_layers=hidden_layers)
    raise ValueError(f"Unknown task: {name}")


def _print_progress(summary: GenerationSummary) -> None:
    print(
        f"gen={summary.generation:03d} "
        f"best_obj={summary.best_objective:.4f} "
        f"best_mix={summary.best_combined:.4f} "
        f"avg_obj={summary.average_objective:.4f} "
        f"archive={summary.archive_size}"
    )


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Run an evolving AI experiment.")
    parser.add_argument(
        "--task",
        choices=("code-agent", "sequence", "xor"),
        default="code-agent",
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
    parser.add_argument("--seed", type=int, default=7, help="Random seed.")
    parser.add_argument(
        "--novelty-weight",
        type=float,
        default=0.25,
        help="Blend factor between objective fitness and novelty.",
    )
    parser.add_argument(
        "--json-out",
        type=Path,
        help="Optional path to save the full experiment report as JSON.",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)

    if args.task == "code-agent":
        default_hidden = (48, 32, 24)
    elif args.task == "sequence":
        default_hidden = (12, 8)
    else:
        default_hidden = (6, 6)
    hidden_layers = _parse_hidden_layers(args.hidden, default_hidden)
    task = _build_task(args.task, hidden_layers)
    config = EvolutionConfig(
        population_size=args.population,
        generations=args.generations,
        novelty_weight=args.novelty_weight,
        seed=args.seed,
    )
    engine = EvolutionEngine(task=task, config=config)
    result = engine.run(progress_callback=_print_progress)

    print(
        f"best task={result.task_name} "
        f"objective={result.best.objective_score:.4f} "
        f"combined={result.best.combined_score:.4f} "
        f"archive={result.archive_size}"
    )

    if hasattr(task, "render_candidate_report"):
        print()
        best_network = NeuralNetwork.from_genome(task.shape, result.best.genome)
        print(task.render_candidate_report(best_network))

    if args.json_out:
        engine.save_result(args.json_out, result)
        print(f"saved report to {args.json_out}")

    return 0
