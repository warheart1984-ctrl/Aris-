"""ForgeEval evaluator registry."""

from forge_eval.evaluators.analyze_shared import InvalidEvaluationRequest
from forge_eval.evaluators.io_tests import evaluate_io_tests
from forge_eval.evaluators.llm_rubric import evaluate_llm_rubric
from forge_eval.evaluators.repo_patch import evaluate_repo_patch

EVALUATORS = {
    "io_tests": evaluate_io_tests,
    "llm_rubric": evaluate_llm_rubric,
    "repo_patch": evaluate_repo_patch,
}

__all__ = [
    "EVALUATORS",
    "InvalidEvaluationRequest",
    "evaluate_io_tests",
    "evaluate_llm_rubric",
    "evaluate_repo_patch",
]
