import unittest

from evolving_ai.code_agents import CodeWritingBenchmarkTask
from evolving_ai.config import EvolutionConfig
from evolving_ai.engine import EvolutionEngine
from evolving_ai.network import NeuralNetwork


class CodeAgentTests(unittest.TestCase):
    def test_code_writing_benchmark_evolves_working_programs(self) -> None:
        task = CodeWritingBenchmarkTask(hidden_layers=(24, 18), memory_size=6)
        self.assertGreaterEqual(len(task.problems), 10)
        self.assertGreater(task.shape.input_size, 40)
        self.assertGreater(task.shape.output_size, 40)

        config = EvolutionConfig(
            population_size=40,
            generations=12,
            novelty_weight=0.2,
            mutation_probability=0.22,
            seed=9,
        )
        result = EvolutionEngine(task, config).run()

        self.assertGreater(result.best.objective_score, 0.25)

        best_network = NeuralNetwork.from_genome(task.shape, result.best.genome)
        report = task.render_candidate_report(best_network)
        self.assertIn("def sum_two", report)
        self.assertIn("def median_three", report)
        self.assertIn("def distance_to_span", report)


if __name__ == "__main__":
    unittest.main()
