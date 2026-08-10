from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Callable, Optional, TYPE_CHECKING
import json
import uuid
import asyncio

if TYPE_CHECKING:
    from evolving_ai import (
        CEPEvolutionEngine,
        IntentPattern,
        ConstitutionalGenome,
        EvidenceRecord,
        LineageRecord,
        ConstitutionalCandidate,
        CEPGenerationSummary,
        PromotionTier,
        MutationOperatorType,
        EvolutionConfig,
    )
    from evolving_ai.core import NoveltyArchive, Task

from .cep_integration import CEPArisIntegration, CEPArisIntegrationConfig
from .cep_ciems import CIEMSForgeEvaluator, CEPForgeEvaluatorAdapter, CIEMSEvaluationConfig
from .cep_sovereignx import SovereignXRenderer, SMERenderResult, FLUXIngestResult, SovereignXRenderConfig


@dataclass(frozen=True, slots=True)
class CEPOrchestrationConfig:
    # ARIS integration
    aris_repo_root: Path
    aris_runtime_root: Path
    cep_storage: Path

    # CIEMS evaluation
    ciems_conformance_mode: str = "repo_patch"
    forge_eval_url: str = "http://localhost:8081"
    forge_url: str = "http://localhost:8080"

    # Sovereign X rendering
    sme_endpoint: str = "http://localhost:8082"
    flux_endpoint: str = "http://localhost:8083"
    render_quality: str = "high"
    render_every_n_generations: int = 5
    render_best_only: bool = True

    # Governance
    shield_enabled: bool = True
    memory_integration: bool = True
    logbook_integration: bool = True

    # Promotion thresholds
    promotion_threshold_substrate: float = 0.7
    promotion_threshold_promotion: float = 0.85


@dataclass(frozen=True, slots=True)
class CEPRunResult:
    run_id: str
    intent_id: str
    best_genome: Optional[ConstitutionalGenome]
    best_fitness: float
    best_fitness_receipt: dict[str, float]
    promotions: dict[str, int]
    governance_result: dict[str, Any]
    render_results: list[SMERenderResult]
    flux_results: list[FLUXIngestResult]
    evidence_stored: list[str]
    lineage_stored: list[str]
    started_at: str
    completed_at: str


class CEPOrchestrationService:
    """
    Unified CEP-1 orchestration service integrating:
    - ARIS (governance, law, halls, memory, logbook, shield)
    - CIEMS via Forge/ForgeEval (conformance + NFC narrative fitness)
    - Sovereign X via SME/FLUX (rendering + embeddings)
    """

    def __init__(self, config: CEPOrchestrationConfig) -> None:
        self.config = config
        self.config.cep_storage.mkdir(parents=True, exist_ok=True)

        # Initialize integrations
        self.aris_integration = CEPArisIntegration(CEPArisIntegrationConfig(
            repo_root=config.aris_repo_root,
            runtime_root=config.aris_runtime_root,
            cep_storage=config.cep_storage,
            promotion_threshold_substrate=config.promotion_threshold_substrate,
            promotion_threshold_promotion=config.promotion_threshold_promotion,
            shield_enabled=config.shield_enabled,
            memory_integration=config.memory_integration,
            logbook_integration=config.logbook_integration,
        ))

        self.ciems_evaluator = CEPForgeEvaluatorAdapter(CIEMSEvaluationConfig(
            forge_eval_url=config.forge_eval_url,
            forge_url=config.forge_url,
            conformance_mode=config.ciems_conformance_mode,
        ))

        self.sovereignx_renderer = SovereignXRenderer(SovereignXRenderConfig(
            sme_endpoint=config.sme_endpoint,
            flux_endpoint=config.flux_endpoint,
            default_quality=config.render_quality,
        ))

        # State
        self.active_runs: dict[str, dict[str, Any]] = {}
        self.run_results: dict[str, CEPRunResult] = {}

    def _utc_now(self) -> str:
        return datetime.now(UTC).isoformat()

    def create_intent(
        self,
        blueprint: str,
        narrative: str = "",
        motifs: tuple[str, ...] = (),
        emotional_curve: tuple[tuple[float, float], ...] = (),
        pacing_target: tuple[float, ...] = (),
        source: str = "orchestration",
        metadata: Optional[dict[str, Any]] = None,
    ) -> "IntentPattern":
        """Create a new IntentPattern for CEP evolution."""
        from evolving_ai import IntentPattern
        intent = IntentPattern(
            id=str(uuid.uuid4())[:8],
            blueprint=blueprint,
            narrative=narrative,
            motifs=motifs,
            emotional_curve=emotional_curve,
            pacing_target=pacing_target,
            metadata={
                "source": source,
                "created_at": self._utc_now(),
                **(metadata or {}),
            },
        )
        return intent

    def create_intent_from_blueprint(self, blueprint_id: str, blueprint_text: str) -> "IntentPattern":
        return self.aris_integration.create_intent_from_blueprint(blueprint_id, blueprint_text)

    def create_intent_from_directive(
        self,
        directive: str,
        purpose: str,
        target_scopes: list[str],
    ) -> "IntentPattern":
        return self.aris_integration.create_intent_from_operator_directive(
            directive, purpose, target_scopes
        )

    async def run_cep_evolution(
        self,
        intent: IntentPattern,
        task: Task,
        config: EvolutionConfig,
        progress_callback: Optional[Callable[[CEPGenerationSummary], None]] = None,
    ) -> CEPRunResult:
        """
        Run full CEP-1 evolution with all integrations.

        This is the main entry point for CEP-1 orchestration.
        """
        run_id = f"cep_{intent.id}_{uuid.uuid4().hex[:8]}"
        started_at = self._utc_now()

        # Track run
        self.active_runs[run_id] = {
            "intent_id": intent.id,
            "config": config.to_dict() if hasattr(config, 'to_dict') else str(config),
            "started_at": started_at,
            "status": "running",
        }

        # Custom evaluator using CIEMS
        original_evaluate = self.aris_integration.forge.evaluate

        def ciems_evaluate(genome: ConstitutionalGenome, intent: IntentPattern) -> EvidenceRecord:
            return self.ciems_evaluator.evaluate(genome, intent)

        # Monkey-patch for CIEMS evaluation
        self.aris_integration.forge.evaluate = ciems_evaluate

        try:
            # Run evolution with ARIS governance
            run_result = self.aris_integration.run_cep_evolution(
                intent=intent,
                task=task,
                config=config,
                progress_callback=progress_callback,
            )

            engine = run_result["engine"]
            governance = run_result["governance"]

            # Render best genomes via Sovereign X
            render_results = []
            flux_results = []

            if self.config.render_best_only:
                genomes_to_render = [run_result["result"].best.genome] if run_result["result"].best else []
            else:
                # Collect from all promotion tiers
                genomes_to_render = []
                for tier in [PromotionTier.PROMOTION, PromotionTier.SUBSTRATE, PromotionTier.SUBSTRATION]:
                    genomes_to_render.extend(engine.promotion_tiers.get(tier, []))

            for i, genome in enumerate(genomes_to_render):
                if i % self.config.render_every_n_generations == 0:
                    try:
                        render_result, flux_result = await self.sovereignx_renderer.render_and_ingest(
                            genome, intent, self.config.render_quality
                        )
                        render_results.append(render_result)
                        flux_results.append(flux_result)
                    except Exception as e:
                        # Log but continue
                        print(f"Render failed for {genome.lineage_id}: {e}")

            # Collect evidence and lineage paths
            evidence_stored = governance.get("evidence_stored", [])
            lineage_stored = []  # Would be populated from lineage store

            completed_at = self._utc_now()

            result = CEPRunResult(
                run_id=run_id,
                intent_id=intent.id,
                best_genome=run_result["result"].best.genome if run_result["result"].best else None,
                best_fitness=run_result["result"].best.overall_fitness if run_result["result"].best else 0.0,
                best_fitness_receipt=run_result["result"].best.fitness_receipt if run_result["result"].best else {},
                promotions={tier.value: len(genomes) for tier, genomes in engine.promotion_tiers.items()},
                governance_result=governance,
                render_results=render_results,
                flux_results=flux_results,
                evidence_stored=evidence_stored,
                lineage_stored=lineage_stored,
                started_at=started_at,
                completed_at=completed_at,
            )

            self.run_results[run_id] = result
            self.active_runs[run_id]["status"] = "completed"
            self.active_runs[run_id]["completed_at"] = completed_at
            self.active_runs[run_id]["result"] = result

            return result

        finally:
            # Restore original evaluator
            self.aris_integration.forge.evaluate = original_evaluate

    def run_cep_evolution_sync(
        self,
        intent: IntentPattern,
        task: Task,
        config: EvolutionConfig,
        progress_callback: Optional[Callable[[CEPGenerationSummary], None]] = None,
    ) -> CEPRunResult:
        """Synchronous wrapper for run_cep_evolution."""
        return asyncio.run(self.run_cep_evolution(intent, task, config, progress_callback))

    def get_run_result(self, run_id: str) -> Optional[CEPRunResult]:
        return self.run_results.get(run_id)

    def get_run_status(self, run_id: str) -> Optional[dict[str, Any]]:
        return self.active_runs.get(run_id)

    def list_runs(self, intent_id: Optional[str] = None) -> list[dict[str, Any]]:
        runs = list(self.active_runs.values())
        if intent_id:
            runs = [r for r in runs if r.get("intent_id") == intent_id]
        return runs

    def list_intents(self) -> list[IntentPattern]:
        """List all stored intents."""
        intents = []
        for intent_file in self.config.cep_storage.joinpath("intents").glob("*.json"):
            with open(intent_file) as f:
                data = json.load(f)
                intents.append(IntentPattern.from_dict(data))
        return intents

    async def render_genome(
        self,
        genome: ConstitutionalGenome,
        intent: IntentPattern,
        quality: Optional[str] = None,
    ) -> tuple[SMERenderResult, FLUXIngestResult]:
        """Render a single genome via Sovereign X."""
        return await self.sovereignx_renderer.render_and_ingest(genome, intent, quality)

    async def close(self) -> None:
        """Close all connections."""
        await self.sovereignx_renderer.close()

    @classmethod
    def create_for_runtime(cls, runtime: Any) -> "CEPOrchestrationService":
        """Create CEPOrchestrationService from an ARIS runtime instance."""
        config = CEPOrchestrationConfig(
            aris_repo_root=runtime.repo_root,
            aris_runtime_root=runtime.runtime_root,
            cep_storage=runtime.runtime_root / "cep",
        )
        return cls(config)


def create_cep_orchestration(
    aris_repo_root: Path,
    aris_runtime_root: Path,
    cep_storage: Optional[Path] = None,
    **overrides: Any,
) -> CEPOrchestrationService:
    """Factory to create CEPOrchestrationService with defaults."""
    if cep_storage is None:
        cep_storage = aris_runtime_root / "cep"

    config = CEPOrchestrationConfig(
        aris_repo_root=aris_repo_root,
        aris_runtime_root=aris_runtime_root,
        cep_storage=cep_storage,
        **overrides,
    )
    return CEPOrchestrationService(config)