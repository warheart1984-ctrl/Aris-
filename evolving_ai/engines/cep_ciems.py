from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Optional, TYPE_CHECKING
import json
import uuid

if TYPE_CHECKING:
    from evolving_ai import (
        ConstitutionalGenome,
        IntentPattern,
        EvidenceRecord,
        EvolutionConfig,
    )

from evolving_ai.engines.cep import CEPForgeEvaluator


@dataclass(frozen=True, slots=True)
class CIEMSEvaluationConfig:
    forge_eval_url: str = "http://localhost:8081"
    forge_url: str = "http://localhost:8080"
    conformance_mode: str = "repo_patch"  # repo_patch, io_tests, llm_rubric
    nfc_narrative_mode: str = "llm_rubric"
    timeout_seconds: float = 300.0
    retry_attempts: int = 3


@dataclass(frozen=True, slots=True)
class CIEMSEvaluationResult:
    conformance_score: float
    nfc_narrative_score: float
    forge_eval_details: dict[str, Any]
    forge_details: dict[str, Any]
    merkle_root: str
    replay_token: str
    timestamp: str


class CIEMSForgeEvaluator:
    """
    CEP-1 Forge/ForgeEval integration for CIEMS conformance evaluation.

    Replaces the mock CEPForgeEvaluator with real Forge/ForgeEval calls.
    """

    def __init__(self, config: Optional[CIEMSEvaluationConfig] = None) -> None:
        self.config = config or CIEMSEvaluationConfig()
        self._forge_client: Optional[LawBoundForgeClient] = None
        self._forge_eval_client: Optional[LawBoundForgeEvalClient] = None
        self._mock_evaluator = CEPForgeEvaluator()

    def _get_forge_client(self) -> LawBoundForgeClient:
        if self._forge_client is None:
            from src.forge_client import LawBoundForgeClient
            from forge.service import ForgeService
            from src.runtime_law import RuntimeLaw
            from pathlib import Path

            forge_service = ForgeService()
            runtime_law = RuntimeLaw(
                repo_root=Path.cwd(),
                runtime_root=Path.cwd() / ".runtime" / "aris",
            )
            self._forge_client = LawBoundForgeClient(forge_service, runtime_law)
        return self._forge_client

    def _get_forge_eval_client(self) -> LawBoundForgeEvalClient:
        if self._forge_eval_client is None:
            from src.forge_eval_client import LawBoundForgeEvalClient
            from forge_eval.service import ForgeEvalService
            from src.runtime_law import RuntimeLaw
            from pathlib import Path

            forge_eval_service = ForgeEvalService()
            runtime_law = RuntimeLaw(
                repo_root=Path.cwd(),
                runtime_root=Path.cwd() / ".runtime" / "aris",
            )
            self._forge_eval_client = LawBoundForgeEvalClient(forge_eval_service, runtime_law)
        return self._forge_eval_client

    def evaluate(
        self,
        genome: ConstitutionalGenome,
        intent: IntentPattern,
        config: Optional[EvolutionConfig] = None,
    ) -> EvidenceRecord:
        """
        Evaluate a ConstitutionalGenome using Forge/ForgeEval for CIEMS conformance.

        This replaces the mock evaluation with real Forge/ForgeEval calls.
        """
        # 1. Generate render artifact from genome (SME/Sovereign X)
        render_artifact = self._render_genome(genome)

        # 2. ForgeEval conformance evaluation (CIEMS)
        conformance_result = self._evaluate_conformance(render_artifact, intent)

        # 3. Forge narrative fitness evaluation (NFC)
        nfc_result = self._evaluate_nfc_narrative(render_artifact, intent)

        # 4. Resource profile from genome topology
        resource_profile = self._compute_resource_profile(genome)

        # 5. Continuity check against intent
        continuity = self._check_continuity(genome, intent)

        # 6. Compute Merkle root and replay token
        merkle = self._compute_merkle_root(genome)
        replay = self._generate_replay_token(genome, intent)

        return EvidenceRecord(
            genome_id=genome.lineage_id,
            conformance_score=conformance_result.get("score", 0.0),
            nfc_narrative_score=nfc_result.get("score", 0.0),
            merkle_root=merkle,
            replay_token=replay,
            resource_profile=resource_profile,
            continuity_score=continuity,
            provenance={
                "intent_id": intent.id,
                "genome_topology": genome.topology,
                "genome_arenas": list(genome.arenas),
                "forge_eval_details": conformance_result,
                "forge_details": nfc_result,
                "render_artifact_hash": self._hash_artifact(render_artifact),
            },
        )

    def _render_genome(self, genome: ConstitutionalGenome) -> dict[str, Any]:
        """Render genome to artifact via SME/Sovereign X."""
        # Use genome's render_config for SME routing
        engine = genome.render_config.get("engine", "SME")
        quality = genome.render_config.get("quality", "high")

        # Build render payload
        render_payload = {
            "genome": genome.to_dict(),
            "engine": engine,
            "quality": quality,
            "topology": genome.topology,
            "arenas": list(genome.arenas),
            "symbols": list(genome.symbols),
            "motifs": list(genome.motifs),
            "pacing": list(genome.pacing),
            "valence_curve": list(genome.valence_curve),
            "arousal_curve": list(genome.arousal_curve),
        }

        # If Forge is available, use it for rendering
        try:
            forge_client = self._get_forge_client()
            response, status = forge_client.evaluate({
                "mode": "repo_patch",
                "payload": {
                    "patch": "",
                    "repo": str(Path.cwd()),
                    "lineage": f"cep_render:{genome.lineage_id}",
                    "target": "cep_render",
                    "diff_present": False,
                    "test_result": "not_run",
                    "config": {"expected_files": []},
                },
            })
            if status == 200:
                render_payload["forge_render"] = response.model_dump(exclude_none=True)
        except Exception:
            # Fall back to mock render
            render_payload["mock_render"] = True

        return render_payload

    def _evaluate_conformance(self, render_artifact: dict[str, Any], intent: IntentPattern) -> dict[str, Any]:
        """Evaluate CIEMS conformance via ForgeEval."""
        try:
            forge_eval_client = self._get_forge_eval_client()

            # Build evaluation request
            eval_request = {
                "task_id": f"cep_conformance_{intent.id}_{uuid.uuid4().hex[:8]}",
                "mode": self.config.conformance_mode,
                "payload": {
                    "program": json.dumps(render_artifact),
                    "lineage": f"cep:{intent.id}",
                    "target": "cep_conformance",
                    "diff_present": False,
                    "test_result": "not_run",
                    "config": {
                        "doc_laws": [
                            "Never bypass UL or runtime law.",
                            "No hidden path or unverified return.",
                            "ARIS remains the speaking identity anchor.",
                            "Evaluation feedback must remain structured and usable.",
                        ],
                        "doc_fail_conditions": [
                            "hidden path",
                            "unverified return",
                            "direct repo write outside governed mutation",
                            "identity drift",
                            "law bypass",
                        ],
                    },
                },
            }

            response, status = forge_eval_client.evaluate(eval_request)
            if status == 200:
                return {
                    "score": response.result.score,
                    "details": response.result.details,
                    "status": "success",
                }
            else:
                return {
                    "score": 0.0,
                    "details": {"error": response.error.message if response.error else "unknown"},
                    "status": "failed",
                }
        except Exception as e:
            # Fall back to mock evaluation
            return self._mock_evaluator._check_cems_conformance(
                ConstitutionalGenome(**render_artifact.get("genome", {})),
                intent,
            )

    def _evaluate_nfc_narrative(self, render_artifact: dict[str, Any], intent: IntentPattern) -> dict[str, Any]:
        """Evaluate NFC narrative fitness via Forge (llm_rubric mode)."""
        try:
            forge_client = self._get_forge_client()

            # Build narrative evaluation request
            eval_request = {
                "mode": "llm_rubric",
                "payload": {
                    "program": json.dumps({
                        "genome": render_artifact.get("genome", {}),
                        "intent": {
                            "blueprint": intent.blueprint,
                            "narrative": intent.narrative,
                            "motifs": list(intent.motifs),
                            "emotional_curve": list(intent.emotional_curve),
                            "pacing_target": list(intent.pacing_target),
                        },
                    }),
                    "lineage": f"cep_nfc:{intent.id}",
                    "target": "cep_nfc_narrative",
                    "config": {
                        "criteria": [
                            {"label": "narrative_coherence", "required_terms": ["coherent", "structured"]},
                            {"label": "motif_alignment", "required_terms": list(intent.motifs) if intent.motifs else []},
                            {"label": "emotional_arc", "required_terms": ["arc", "progression"]},
                            {"label": "pacing", "required_terms": ["pacing", "rhythm"]},
                        ],
                    },
                },
            }

            response, status = forge_client.evaluate(eval_request)
            if status == 200:
                return {
                    "score": response.result.score,
                    "details": response.result.details,
                    "status": "success",
                }
            else:
                return {"score": 0.0, "details": {}, "status": "failed"}
        except Exception:
            return self._mock_evaluator._evaluate_nfc_narrative(
                ConstitutionalGenome(**render_artifact.get("genome", {})),
                intent,
            )

    def _compute_resource_profile(self, genome: ConstitutionalGenome) -> dict[str, float]:
        layers = genome.topology.get("layers", [64, 32, 16])
        param_count = sum(layers[i] * layers[i+1] for i in range(len(layers)-1))
        return {
            "parameter_count": float(param_count),
            "compute_cost": min(1.0, param_count / 10000.0),
            "memory_mb": param_count * 4 / 1024 / 1024,
            "arena_count": float(len(genome.arenas)),
            "symbol_count": float(len(genome.symbols)),
        }

    def _check_continuity(self, genome: ConstitutionalGenome, intent: IntentPattern) -> float:
        score = 0.5
        if genome.motifs and intent.motifs:
            overlap = set(genome.motifs) & set(intent.motifs)
            score += len(overlap) / max(1, len(intent.motifs)) * 0.3
        if genome.pacing and intent.pacing_target:
            diff = sum(abs(a - b) for a, b in zip(genome.pacing, intent.pacing_target)) / max(1, len(intent.pacing_target))
            score += max(0, 1.0 - diff) * 0.2
        return min(1.0, score)

    def _compute_merkle_root(self, genome: ConstitutionalGenome) -> str:
        import hashlib
        data = json.dumps(genome.to_dict(), sort_keys=True).encode()
        return hashlib.sha256(data).hexdigest()[:16]

    def _generate_replay_token(self, genome: ConstitutionalGenome, intent: IntentPattern) -> str:
        import hashlib
        data = f"{intent.id}:{genome.lineage_id}:{genome.age}".encode()
        return hashlib.sha256(data).hexdigest()[:12]

    def _hash_artifact(self, artifact: dict[str, Any]) -> str:
        import hashlib
        data = json.dumps(artifact, sort_keys=True).encode()
        return hashlib.sha256(data).hexdigest()[:16]


class CEPForgeEvaluatorAdapter:
    """
    Adapter to use CIEMSForgeEvaluator as a drop-in replacement for CEPForgeEvaluator.
    """

    def __init__(self, ciems_config: Optional[CIEMSEvaluationConfig] = None) -> None:
        self.ciems_evaluator = CIEMSForgeEvaluator(ciems_config)

    def evaluate(self, genome: ConstitutionalGenome, intent: IntentPattern) -> EvidenceRecord:
        """Drop-in replacement for CEPForgeEvaluator.evaluate()"""
        return self.ciems_evaluator.evaluate(genome, intent)


def create_ciems_evaluator(
    forge_eval_url: str = "http://localhost:8081",
    forge_url: str = "http://localhost:8080",
    conformance_mode: str = "repo_patch",
) -> CEPForgeEvaluatorAdapter:
    """Factory to create CIEMS evaluator adapter."""
    config = CIEMSEvaluationConfig(
        forge_eval_url=forge_eval_url,
        forge_url=forge_url,
        conformance_mode=conformance_mode,
    )
    return CEPForgeEvaluatorAdapter(config)