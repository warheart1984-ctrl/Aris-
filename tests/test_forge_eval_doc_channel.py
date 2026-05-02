from __future__ import annotations

from pathlib import Path
import shutil
import unittest
import uuid

from forge_eval.schemas import EvaluationResult, EvaluationSuccessResponse

from src.forge_eval_client import LawBoundForgeEvalClient
from src.runtime_law import RuntimeLaw


REPO_ROOT = Path(__file__).resolve().parents[1]
TEST_RUNTIME_ROOT = REPO_ROOT / ".runtime" / "forge-eval-doc-channel-test"


def _make_runtime() -> tuple[RuntimeLaw, Path]:
    TEST_RUNTIME_ROOT.mkdir(parents=True, exist_ok=True)
    root = TEST_RUNTIME_ROOT / f"case-{uuid.uuid4().hex[:10]}"
    root.mkdir(parents=True, exist_ok=True)
    return RuntimeLaw(repo_root=REPO_ROOT, runtime_root=root), root


class _InnerEval:
    def __init__(self) -> None:
        self.payload: dict | None = None

    def evaluate(self, payload: dict):
        self.payload = dict(payload)
        return (
            EvaluationSuccessResponse(
                task_id=str(payload.get("task_id") or "task"),
                mode=str(payload.get("mode") or "io_tests"),
                result=EvaluationResult(score=0.95, details={"checks": []}),
            ),
            200,
        )


class ForgeEvalDocChannelTests(unittest.TestCase):
    def test_doc_channel_is_injected_and_enforced(self) -> None:
        runtime_law, root = _make_runtime()
        self.addCleanup(lambda: shutil.rmtree(root, ignore_errors=True))
        inner = _InnerEval()
        client = LawBoundForgeEvalClient(inner, runtime_law)

        response, status_code = client.evaluate(
            {
                "task_id": "alpha",
                "mode": "io_tests",
                "payload": {
                    "program": "def main():\n    print('unsafe')\n",
                    "config": {},
                },
            }
        )

        raw = response.model_dump(exclude_none=True)
        self.assertEqual(status_code, 200)
        self.assertIsNotNone(inner.payload)
        self.assertIn("doc_dsl", inner.payload["payload"]["config"])
        self.assertEqual(inner.payload["payload"]["config"]["doc_channel_namespace"], "aris.python")
        self.assertLessEqual(raw["result"]["score"], 0.1)
        self.assertTrue(raw["result"]["details"]["violations"])
        self.assertTrue(any(not item["passed"] for item in raw["result"]["details"]["checks"]))
        self.assertEqual(raw["result"]["details"]["doc_channel"]["namespace"], "aris.python")


if __name__ == "__main__":
    unittest.main()
