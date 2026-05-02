from __future__ import annotations

import sys
import types
from pathlib import Path
import shutil
import tempfile
import unittest

if "requests" not in sys.modules:
    requests_stub = types.ModuleType("requests")

    class RequestException(Exception):
        pass

    def _blocked_post(*args, **kwargs):
        raise RequestException("requests transport is unavailable in this test runtime")

    requests_stub.RequestException = RequestException
    requests_stub.post = _blocked_post
    sys.modules["requests"] = requests_stub

from evolving_ai.aris.runtime import ArisRuntime
from forge_eval.schemas import EvaluationResult, EvaluationSuccessResponse
from src.forge_eval_client import LawBoundForgeEvalClient


REPO_ROOT = Path(__file__).resolve().parents[1]


class _RecordingForgeEvalInner:
    def __init__(self, responses):
        self.responses = list(responses)
        self.requests: list[dict] = []

    def evaluate(self, payload):
        self.requests.append(dict(payload))
        if not self.responses:
            raise AssertionError("No ForgeEval response left for test")
        return self.responses.pop(0)


def _response(*, score: float, checks: list[dict] | None = None):
    return (
        EvaluationSuccessResponse(
            task_id="cand",
            mode="io_tests",
            result=EvaluationResult(score=score, details={"checks": checks or []}),
        ),
        200,
    )


class ArisLogIngestionTests(unittest.TestCase):
    def setUp(self) -> None:
        self._temp_dir = Path(tempfile.mkdtemp(prefix="aris-log-ingest-"))
        self.addCleanup(lambda: shutil.rmtree(self._temp_dir, ignore_errors=True))

    def _runtime(self) -> ArisRuntime:
        return ArisRuntime(repo_root=REPO_ROOT, runtime_root=self._temp_dir / "runtime")

    def test_fame_candidate_uses_law_bound_forge_eval_and_hits_hall_of_fame(self) -> None:
        runtime = self._runtime()
        before_doc = runtime.runtime_law.doc_channel.payload()
        inner = _RecordingForgeEvalInner(
            [
                _response(score=0.94, checks=[{"label": "safe", "passed": True}]),
            ]
        )
        runtime.forge_eval = LawBoundForgeEvalClient(inner, runtime.runtime_law)

        result = runtime.ingest_codex_log(
            {
                "task": "Add a safe helper",
                "actions": [
                    {
                        "type": "edit",
                        "file": "sample.py",
                        "code": "def helper():\n    return 1\n",
                    }
                ],
                "result": "success",
            },
            session_id="alpha",
        )

        self.assertTrue(result["ok"])
        self.assertEqual(result["counts"]["FAME"], 1)
        self.assertEqual(result["results"][0]["classification"], "FAME")
        self.assertEqual(result["results"][0]["hall_name"], "hall_of_fame")
        self.assertEqual(runtime.hall_of_fame.count(), 1)
        self.assertEqual(runtime.evolve_engine.count(), 1)
        self.assertEqual(runtime.runtime_law.doc_channel.payload(), before_doc)
        request_config = inner.requests[0]["payload"]["config"]
        self.assertIn("doc_laws", request_config)
        self.assertIn("doc_fail_conditions", request_config)

    def test_subthreshold_candidate_routes_to_hall_of_shame(self) -> None:
        runtime = self._runtime()
        inner = _RecordingForgeEvalInner(
            [
                _response(score=0.42, checks=[{"label": "safe", "passed": True}]),
            ]
        )
        runtime.forge_eval = LawBoundForgeEvalClient(inner, runtime.runtime_law)

        result = runtime.ingest_codex_log(
            {
                "task": "Add a weak helper",
                "actions": [
                    {
                        "type": "edit",
                        "file": "sample.py",
                        "code": "def helper(value):\n    return value\n",
                    }
                ],
                "result": "success",
            },
            session_id="beta",
        )

        self.assertEqual(result["counts"]["SHAME"], 1)
        self.assertEqual(result["results"][0]["classification"], "SHAME")
        self.assertEqual(result["results"][0]["hall_name"], "hall_of_shame")
        self.assertEqual(runtime.hall_of_shame.count(), 1)
        self.assertEqual(runtime.hall_of_fame.count(), 0)

    def test_doc_channel_violation_routes_to_discard_and_keeps_raw_log_out_of_trace(self) -> None:
        runtime = self._runtime()
        inner = _RecordingForgeEvalInner(
            [
                _response(score=0.99, checks=[{"label": "safe", "passed": True}]),
            ]
        )
        runtime.forge_eval = LawBoundForgeEvalClient(inner, runtime.runtime_law)

        result = runtime.ingest_codex_log(
            "TOP SECRET RAW LOG TRAIL\n```python\ndef helper():\n    print('x')\n```",
            session_id="gamma",
        )

        self.assertEqual(result["counts"]["DISGRACE"], 1)
        self.assertEqual(result["results"][0]["classification"], "DISGRACE")
        self.assertEqual(result["results"][0]["hall_name"], "hall_of_discard")
        self.assertEqual(runtime.hall_of_discard.count(), 1)
        self.assertTrue(result["results"][0]["evaluation"]["violations"])
        trace_text = (runtime.runtime_root / "evolve_engine" / "classified-traces.jsonl").read_text(
            encoding="utf-8"
        )
        self.assertNotIn("TOP SECRET RAW LOG TRAIL", trace_text)
        self.assertNotIn("output_text", trace_text)

    def test_trace_store_is_reconstructable(self) -> None:
        runtime = self._runtime()
        inner = _RecordingForgeEvalInner(
            [
                _response(score=0.91, checks=[{"label": "safe", "passed": True}]),
            ]
        )
        runtime.forge_eval = LawBoundForgeEvalClient(inner, runtime.runtime_law)

        runtime.ingest_codex_log(
            {
                "task": "Extract a reusable helper",
                "actions": [
                    {
                        "type": "edit",
                        "file": "tools.py",
                        "code": "def choose(items):\n    return items[0]\n",
                    }
                ],
                "result": "success",
            },
            session_id="delta",
        )

        trace = runtime.list_evolve_traces(limit=1)[0]
        self.assertIn("packet", trace)
        self.assertIn("candidate", trace)
        self.assertIn("evaluation", trace)
        self.assertIn("classification", trace)
        self.assertIn("hall", trace)
        self.assertTrue(trace["trace_id"])


if __name__ == "__main__":
    unittest.main()
