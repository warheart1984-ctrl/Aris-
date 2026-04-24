import unittest

from evolving_ai.config import EvolutionConfig, NetworkShape


class ConfigTests(unittest.TestCase):
    def test_parameter_count_matches_network_layout(self) -> None:
        shape = NetworkShape(input_size=3, hidden_layers=(4, 2), output_size=1)
        self.assertEqual(shape.parameter_count, 29)

    def test_elite_count_is_at_least_one(self) -> None:
        config = EvolutionConfig(population_size=10, elite_fraction=0.01)
        self.assertEqual(config.elite_count, 1)


if __name__ == "__main__":
    unittest.main()
