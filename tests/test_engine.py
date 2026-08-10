import unittest

from evolving_ai.core import (
    EvolutionConfig,
    EvolutionEngine,
    XorTask,
    SequencePredictionTask,
    DenseGenome,
    NoveltyArchive,
)


class EngineTests(unittest.TestCase):
    def test_engine_runs_and_improves(self) -> None:
        task = SequencePredictionTask(hidden_layers=(6, 4))
        config = EvolutionConfig(population_size=36, generations=8, seed=3)

        # Calculate genome size for this task
        layer_sizes = (task.input_size, *task.hidden_layers, task.output_size)
        genome_size = sum(i * o + o for i, o in zip(layer_sizes, layer_sizes[1:]))

        archive = NoveltyArchive()
        import random
        rng = random.Random(config.seed)
        initial_population = [DenseGenome.random(genome_size, 0.35, rng)
                              for _ in range(config.population_size)]

        engine = EvolutionEngine(config, task, archive, rng=rng)
        result = engine.run(initial_population)

        self.assertIsNotNone(result)
        self.assertGreater(result.fitness, 0.0)

    def test_xor_objective_reaches_reasonable_quality(self) -> None:
        task = XorTask(hidden_layers=(4,))
        config = EvolutionConfig(
            population_size=20,
            generations=15,
            novelty_weight=0.15,
            mutation_rate=0.22,
            seed=11,
        )

        layer_sizes = (task.input_size, *task.hidden_layers, task.output_size)
        genome_size = sum(i * o + o for i, o in zip(layer_sizes, layer_sizes[1:]))

        archive = NoveltyArchive()
        import random
        rng = random.Random(config.seed)
        initial_population = [DenseGenome.random(genome_size, 0.35, rng)
                              for _ in range(config.population_size)]

        engine = EvolutionEngine(config, task, archive, rng=rng)
        result = engine.run(initial_population)

        self.assertGreater(result.fitness, 0.72)


if __name__ == "__main__":
    unittest.main()
