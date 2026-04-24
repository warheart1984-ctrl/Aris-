import unittest

from evolving_ai.config import EvolutionConfig
from evolving_ai.engine import EvolutionEngine
from evolving_ai.tasks import SequencePredictionTask, XorTask


class EngineTests(unittest.TestCase):
    def test_engine_runs_and_keeps_history(self) -> None:
        task = SequencePredictionTask(hidden_layers=(6, 4))
        config = EvolutionConfig(population_size=36, generations=8, seed=3)
        result = EvolutionEngine(task, config).run()

        self.assertEqual(len(result.history), 8)
        self.assertGreater(result.best.objective_score, 0.0)
        self.assertGreater(result.archive_size, 0)

    def test_xor_objective_reaches_reasonable_quality(self) -> None:
        task = XorTask(hidden_layers=(4,))
        config = EvolutionConfig(
            population_size=48,
            generations=30,
            novelty_weight=0.15,
            mutation_probability=0.22,
            seed=11,
        )
        result = EvolutionEngine(task, config).run()

        self.assertGreater(result.best.objective_score, 0.72)


if __name__ == "__main__":
    unittest.main()
