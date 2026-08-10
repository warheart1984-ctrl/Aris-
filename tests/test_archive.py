import unittest

from evolving_ai.core.archive import NoveltyArchive


class ArchiveTests(unittest.TestCase):
    def test_far_behavior_is_more_novel(self) -> None:
        archive = NoveltyArchive(k=2)
        archive.add((0.0, 0.0), fitness=0.5, genome=None)
        archive.add((0.1, 0.1), fitness=0.6, genome=None)

        close_score = archive.novelty((0.15, 0.12))
        far_score = archive.novelty((1.0, 1.0))

        self.assertGreater(far_score, close_score)


if __name__ == "__main__":
    unittest.main()
