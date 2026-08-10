from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Callable, Optional, TYPE_CHECKING
import json
import uuid

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

from evolving_ai.aris.hall_of_fame import HallOfFame
from evolving_ai.aris.hall_of_shame import HallOfShame
from evolving_ai.aris.hall_of_discard import HallOfDiscard
from evolving_ai.aris.memory_bank import GovernedMemoryBank
from evolving_ai.aris.logbook import RepoLogbook
from evolving_ai.aris.shield import ShieldOfTruth1001, DecisionContext
from src.forge_client import LawBoundForgeClient
from src.forge_eval_client import LawBoundForgeEvalClient
from src.runtime_law import RuntimeLaw
from src.forge_eval_client import LawBoundForgeEvalClient
from src.runtime_law import RuntimeLaw


@dataclass(frozen=True, slots=True)
class CEPArisIntegrationConfig:
    repo_root: Path
    runtime_root: Path
    cep_storage: Path
    promotion_threshold_substrate: float = 0.7
    promotion_threshold_promotion: float = 0.85
    min_evidence_strength: float = 0.6
    shield_enabled: bool = True
    memory_integration: bool = True
    logbook_integration: bool = True


class CEPArisIntegration:
    """Integration layer between CEP-1 and ARIS governance, law, and memory systems."""

    def __init__(self, config: CEPArisIntegrationConfig, runtime: Optional["ArisRuntime"] = None) -> None:
        self.config = config
        self.config.cep_storage.mkdir(parents=True, exist_ok=True)

        # ARIS Runtime (provided or created)
        self.runtime = runtime or self._create_runtime(config)

        # CEP-specific storage
        self.evidence_store = config.cep_storage / "evidence"
        self.lineage_store = config.cep_storage / "lineage"
        self.promotion_store = config.cep_storage / "promotions"
        self.intent_store = config.cep_storage / "intents"

        for store in [self.evidence_store, self.lineage_store, self.promotion_store, self.intent_store]:
            store.mkdir(parents=True, exist_ok=True)

        # Shield of Truth 1001 for governance decisions
        self.shield = ShieldOfTruth1001() if config.shield_enabled else None

        # Track active CEP runs
        self.active_runs: dict[str, dict[str, Any]] = {}

    def _create_runtime(self, config: CEPArisIntegrationConfig) -> "ArisRuntime":
        from evolving_ai.aris.runtime import ArisRuntime
        return ArisRuntime(
            repo_root=config.repo_root,
            runtime_root=config.runtime_root,
        )

    def _utc_now(self) -> str:
        return datetime.now(UTC).isoformat()

    def create_intent_from_blueprint(
        self,
        blueprint_id: str,
        blueprint_text: str,
        narrative: str = "",
        motifs: tuple[str, ...] = (),
        emotional_curve: tuple[tuple[float, float], ...] = (),
        pacing_target: tuple[float, ...] = (),
    ) -> IntentPattern:
        """Create an IntentPattern from a Jarvis blueprint or operator directive."""
        intent = IntentPattern(
            id=blueprint_id[:8],
            blueprint=blueprint_text,
            narrative=narrative,
            motifs=motifs,
            emotional_curve=emotional_curve,
            pacing_target=pacing_target,
            metadata={
                "source": "jarvis_blueprint",
                "blueprint_id": blueprint_id,
                "created_at": self._utc_now(),
            },
        )

        # Store intent for traceability
        intent_path = self.intent_store / f"{intent.id}.json"
        intent_path.write_text(json.dumps(intent.to_dict(), indent=2), encoding="utf-8")

        return intent

    def create_intent_from_operator_directive(
        self,
        directive: str,
        purpose: str,
        target_scopes: list[str],
    ) -> IntentPattern:
        """Create an IntentPattern from an operator directive."""
        intent = IntentPattern(
            id=str(uuid.uuid4())[:8],
            blueprint=f"Operator Directive: {directive}",
            narrative=purpose,
            motifs=tuple(set(purpose.lower().split())),
            metadata={
                "source": "operator_directive",
                "directive": directive,
                "purpose": purpose,
                "target_scopes": target_scopes,
                "created_at": self._utc_now(),
            },
        )

        intent_path = self.intent_store / f"{intent.id}.json"
        intent_path.write_text(json.dumps(intent.to_dict(), indent=2), encoding="utf-8")

        return intent

    def run_cep_evolution(
        self,
        intent: IntentPattern,
        task: Task,
        config: EvolutionConfig,
        progress_callback: Optional[Callable[[CEPGenerationSummary], None]] = None,
    ) -> dict[str, Any]:
        """Run CEP evolution with full ARIS governance integration."""
        run_id = f"cep_{intent.id}_{str(uuid.uuid4())[:8]}"

        # Initialize ARIS governance context
        archive = NoveltyArchive(k=config.behavior_neighbors if hasattr(config, 'behavior_neighbors') else 15)

        engine = CEPEvolutionEngine(
            config=config,
            task=task,
            archive=archive,
            intent=intent,
        )

        # Wrap progress callback with governance checks
        def governed_progress(summary: CEPGenerationSummary) -> None:
            # Check shield if enabled
            if self.shield and self.config.shield_enabled:
                ctx = DecisionContext(
                    actor="cep_engine",
                    action_type="cep_generation",
                    input_payload={"generation": summary.generation, "intent_id": intent.id},
                    proposed_output={"summary": summary.__dict__},
                    interpreted_intent=f"CEP generation {summary.generation} for intent {intent.id}",
                )
                evaluation = self.shield.judge(ctx)
                if evaluation.verdict.value in ("quarantined", "fail"):
                    raise RuntimeError(f"Shield rejected CEP generation: {evaluation.explanation}")

            # Log to memory bank if enabled
            if self.config.memory_integration:
                self.runtime.memory_bank.admit_entry(
                    layer="learned_patterns",
                    entry_type="cep_generation",
                    source="cep_engine",
                    summary=f"Generation {summary.generation}: best_fitness={summary.best_fitness:.4f}",
                    content=json.dumps({
                        "generation": summary.generation,
                        "best_fitness": summary.best_fitness,
                        "best_fitness_receipt": summary.best_fitness_receipt,
                        "promotion_counts": summary.promotion_counts,
                    }),
                    tags=("cep", "generation", intent.id),
                )

            # Call user callback
            if progress_callback:
                progress_callback(summary)

        # Run evolution
        result = engine.run(progress_callback=governed_progress)

        # Post-process: ARIS governance on results
        governance_result = self._apply_governance(result, intent, run_id)

        # Store run metadata
        self.active_runs[run_id] = {
            "intent_id": intent.id,
            "config": config.to_dict() if hasattr(config, 'to_dict') else str(config),
            "started_at": self._utc_now(),
            "completed_at": self._utc_now(),
            "best_fitness": result.best.overall_fitness if result.best else 0.0,
            "promotion_tiers": {tier.value: len(genomes) for tier, genomes in engine.promotion_tiers.items()},
            "promotion_records": len(engine.promotion_records),
            "governance": governance_result,
        }

        return {
            "run_id": run_id,
            "intent_id": intent.id,
            "result": result,
            "engine": engine,
            "governance": governance_result,
        }

    def _apply_governance(
        self,
        result: Any,
        intent: IntentPattern,
        run_id: str,
    ) -> dict[str, Any]:
        """Apply ARIS governance to CEP results."""
        governance = {
            "shield_passed": True,
            "memory_entries": [],
            "hall_placements": {},
            "logbook_entry": None,
            "promotions_approved": [],
            "evidence_stored": [],
        }

        if not result.best:
            return governance

        best = result.best
        evidence = best.evidence
        genome = best.genome

        # 1. Shield of Truth 1001 evaluation
        if self.shield and self.config.shield_enabled:
            ctx = DecisionContext(
                actor="cep_engine",
                action_type="cep_promotion_candidate",
                input_payload={
                    "genome_id": genome.lineage_id,
                    "intent_id": intent.id,
                    "fitness_receipt": best.fitness_receipt,
                    "overall_fitness": best.overall_fitness,
                },
                proposed_output={
                    "status": "pending_promotion",
                    "genome": genome.to_dict(),
                    "evidence": evidence.to_dict() if hasattr(evidence, 'to_dict') else {},
                },
                interpreted_intent=f"Evaluate CEP genome {genome.lineage_id} for promotion",
                values_claimed=("verification_requirement", "mutation_integrity", "identity_consistency"),
                mutation=True,
            )
            evaluation = self.shield.judge(ctx)
            governance["shield_passed"] = evaluation.verdict.value == "pass"
            governance["shield_verdict"] = evaluation.verdict.value
            governance["shield_explanation"] = evaluation.explanation

        # 2. Store evidence in ARIS memory
        if self.config.memory_integration:
            entry = self.runtime.memory_bank.admit_entry(
                layer="learned_patterns",
                entry_type="cep_genome",
                source="cep_engine",
                summary=f"CEP genome {genome.lineage_id} for intent {intent.id}",
                content=json.dumps({
                    "genome": genome.to_dict(),
                    "evidence": evidence.to_dict() if hasattr(evidence, 'to_dict') else {},
                    "fitness_receipt": best.fitness_receipt,
                    "overall_fitness": best.overall_fitness,
                }),
                tags=("cep", "genome", intent.id, "promotion_candidate"),
            )
            governance["memory_entries"].append(entry.id)

        # 3. Hall placement based on fitness and shield verdict
        if best.overall_fitness >= self.config.promotion_threshold_promotion and governance["shield_passed"]:
            # Hall of Fame - canonical promotion
            hall_entry = self.runtime.hall_of_fame.record(
                fingerprint=evidence.replay_token,
                lineage_key=f"cep:{intent.id}:{genome.lineage_id}",
                action={"genome_id": genome.lineage_id, "intent_id": intent.id},
                reason=f"CEP promotion: fitness={best.overall_fitness:.4f}, conformance={evidence.conformance_score:.4f}",
                law_results=[],
                guardrails=[],
                operator_decision="cep_auto_promotion",
                forge_eval=[],
                source="cep_engine",
                notes=f"CEP-1 constitutional promotion for intent {intent.id}",
                containment_status="canonical",
            )
            governance["hall_placements"]["hall_of_fame"] = hall_entry["id"]
            governance["promotions_approved"].append("promotion")

        elif best.overall_fitness >= self.config.promotion_threshold_substrate and governance["shield_passed"]:
            # Hall of Shame - substrate (stable but not canonical)
            hall_entry = self.runtime.hall_of_shame.record(
                fingerprint=evidence.replay_token,
                lineage_key=f"cep:{intent.id}:{genome.lineage_id}",
                action={"genome_id": genome.lineage_id, "intent_id": intent.id},
                reason=f"CEP substrate: fitness={best.overall_fitness:.4f}, conformance={evidence.conformance_score:.4f}",
                law_results=[],
                guardrails=[],
                operator_decision="cep_auto_substrate",
                forge_eval=[],
                source="cep_engine",
                notes=f"CEP-1 substrate tier for intent {intent.id}",
                containment_status="stable",
            )
            governance["hall_placements"]["hall_of_shame"] = hall_entry["id"]
            governance["promotions_approved"].append("substrate")

        else:
            # Hall of Discard - experimental/substration
            hall_entry = self.runtime.hall_of_discard.record(
                fingerprint=evidence.replay_token,
                lineage_key=f"cep:{intent.id}:{genome.lineage_id}",
                action={"genome_id": genome.lineage_id, "intent_id": intent.id},
                reason=f"CEP subration: fitness={best.overall_fitness:.4f}, below promotion threshold",
                law_results=[],
                guardrails=[],
                operator_decision="cep_auto_substration",
                forge_eval=[],
                source="cep_engine",
                notes=f"CEP-1 subration tier for intent {intent.id}",
                containment_status="contained",
            )
            governance["hall_placements"]["hall_of_discard"] = hall_entry["id"]
            governance["promotions_approved"].append("substration")

        # 4. Logbook entry for significant promotions
        if self.config.logbook_integration and governance["promotions_approved"]:
            logbook_entry = self.runtime.logbook.append_entry(
                title=f"CEP-1 Promotion: {', '.join(governance['promotions_approved'])}",
                what_changed=[f"Genome {genome.lineage_id} promoted to {p}" for p in governance['promotions_approved']],
                why_it_changed=[f"Intent {intent.id} achieved fitness {best.overall_fitness:.4f} with conformance {evidence.conformance_score:.4f}"],
                how_it_changed=["CEP-1 constitutional evolution with ARIS governance"],
                files_changed=[f"cep/genomes/{genome.lineage_id}.json"],
                verification=[f"Shield verdict: {governance.get('shield_verdict', 'not_evaluated')}", f"Fitness receipt: {best.fitness_receipt}"],
                remaining_risks=["Continued monitoring required for promoted genomes"],
                action_id=run_id,
                fingerprint=evidence.replay_token,
            )
            governance["logbook_entry"] = logbook_entry

        # 5. Store evidence and lineage records
        evidence_path = self.evidence_store / f"{run_id}_{genome.lineage_id}.json"
        evidence_path.write_text(json.dumps(evidence.to_dict() if hasattr(evidence, 'to_dict') else {}, indent=2), encoding="utf-8")
        governance["evidence_stored"].append(str(evidence_path))

        lineage = best.lineage
        lineage_path = self.lineage_store / f"{run_id}_{genome.lineage_id}_lineage.json"
        lineage_path.write_text(json.dumps(lineage.to_dict() if hasattr(lineage, 'to_dict') else {}, indent=2), encoding="utf-8")

        return governance

    def get_run_status(self, run_id: str) -> Optional[dict[str, Any]]:
        return self.active_runs.get(run_id)

    def list_runs(self, intent_id: Optional[str] = None) -> list[dict[str, Any]]:
        runs = list(self.active_runs.values())
        if intent_id:
            runs = [r for r in runs if r.get("intent_id") == intent_id]
        return runs


def create_cep_aris_integration(
    repo_root: Path,
    runtime_root: Path,
    cep_storage: Optional[Path] = None,
) -> CEPArisIntegration:
    """Factory function to create CEP-ARIS integration with defaults."""
    if cep_storage is None:
        cep_storage = runtime_root / "cep"

    config = CEPArisIntegrationConfig(
        repo_root=repo_root,
        runtime_root=runtime_root,
        cep_storage=cep_storage,
    )
    return CEPArisIntegration(config)