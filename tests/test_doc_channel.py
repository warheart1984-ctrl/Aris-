from __future__ import annotations

import unittest

from src.doc_channel import default_doc_channel, evaluate_program_against_doc_channel, parse_doc_channel_text


class DocChannelTests(unittest.TestCase):
    def test_structured_text_parses_into_channel(self) -> None:
        channel = parse_doc_channel_text(
            """
            [GOAL]
            Keep ARIS deterministic.

            [LAWS]
            - Never bypass UL

            [GUIDELINES]
            - Prefer small functions

            [PATTERNS]
            - explicit inputs -> explicit outputs

            [FAIL]
            - hidden path

            [DSL]
            DSL v1
            NAMESPACE: test.python
            LAW no_print:
            ast forbid_call "print"
            """
        )

        self.assertEqual(channel.version, "v1")
        self.assertEqual(channel.namespace, "test.python")
        self.assertEqual(channel.goal, "Keep ARIS deterministic.")
        self.assertIn("Never bypass UL", channel.laws)
        self.assertEqual(channel.rules[0].name, "no_print")

    def test_default_doc_channel_detects_python_law_violations(self) -> None:
        violations = evaluate_program_against_doc_channel(
            """
            import random

            def main():
                global FLAG
                print(random.random())
                return 1
            """,
            default_doc_channel(),
        )

        rule_names = {item["rule"] for item in violations}
        self.assertIn("no_global_state", rule_names)
        self.assertIn("no_random_import", rule_names)
        self.assertIn("no_print", rule_names)


if __name__ == "__main__":
    unittest.main()
