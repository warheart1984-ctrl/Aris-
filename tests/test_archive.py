import unittest

from evolving_ai.archive import NoveltyArchive


class ArchiveTests(unittest.TestCase):
    def test_far_behavior_is_more_novel(self) -> None:
        archive = NoveltyArchive(k_neighbors=2)
        archive.add((0.0, 0.0), objective_score=0.5, generation=0)
        archive.add((0.1, 0.1), objective_score=0.6, generation=1)

        close_score = archive.score((0.15, 0.12), population_behaviors=[])
        far_score = archive.score((1.0, 1.0), population_behaviors=[])

        self.assertGreater(far_score, close_score)


if __name__ == "__main__":
    unittest.main()
