from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from datetime import UTC, datetime
from enum import Enum
from typing import Any, Callable, Generic, List, Optional, Protocol, TypeVar
import hashlib
import json
import numpy as np
import uuid

from ..config import ConfigBase
from ..core import Genome, Task, Archive, NoveltyArchive
from ..core.genome import DenseGenome
from ..engines import (
    EvolutionEngine,
    EvolutionConfig,
    EvaluatedCandidate,
    GenerationSummary,
    EvolutionResult,
)

GenomeT = TypeVar("GenomeT", bound=Genome)


class PromotionTier(str, Enum):
    SUBSTRATION = "substration"
    SUBSTRATE = "substrate"
    PROMOTION = "promotion"


class MutationOperatorType(str, Enum):
    TOPOLOGY = "topology_mutate"
    ARENA = "arena_mutate"
    PACING = "pacing_mutate"
    MOTIF = "motif_mutate"
    EMOTION = "emotion_mutate"


@dataclass(frozen=True, slots=True)
class IntentPattern(ConfigBase):
    CONFIG_TYPE = "intent_pattern"
    id: str = field(default_factory=lambda: str(uuid.uuid4())[:8])
    blueprint: str = ""
    narrative: str = ""
    beats: tuple[str, ...] = ()
    motifs: tuple[str, ...] = ()
    arcs: tuple[str, ...] = ()
    emotional_curve: tuple[tuple[float, float], ...] = ()
    pacing_target: tuple[float, ...] = ()
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_seed_genomes(self, count: int, rng: np.random.Generator) -> List[DenseGenome]:
        genomes = []
        for i in range(count):
            seed = hash((self.id, i, self.blueprint)) % (2**32)
            genome_rng = np.random.default_rng(seed)
            genome = DenseGenome.random(
                size=128,
                mutation_scale=0.1,
                rng=genome_rng,
            )
            genomes.append(genome)
        return genomes


@dataclass(frozen=True, slots=True)
class ConstitutionalGenome(DenseGenome):
    topology: dict[str, Any] = field(default_factory=dict)
    arenas: tuple[str, ...] = ()
    symbols: tuple[str, ...] = ()
    motifs: tuple[str, ...] = ()
    roles: tuple[str, ...] = ()
    pacing: tuple[float, ...] = ()
    transitions: tuple[str, ...] = ()
    valence_curve: tuple[float, ...] = ()
    arousal_curve: tuple[float, ...] = ()
    render_config: dict[str, Any] = field(default_factory=dict)

    @classmethod
    def from_intent(cls, intent: IntentPattern, rng: np.random.Generator) -> "ConstitutionalGenome":
        base = DenseGenome.random(size=128, mutation_scale=0.1, rng=rng)
        return cls(
            weights=base.weights,
            mutation_scale=base.mutation_scale,
            lineage_id=base.lineage_id,
            age=base.age,
            topology={"layers": [64, 32, 16]},
            arenas=("narrative", "emotional", "structural"),
            symbols=tuple(set(intent.motifs)) if intent.motifs else ("core",),
            motifs=intent.motifs,
            roles=("protagonist", "antagonist", "chorus"),
            pacing=intent.pacing_target if intent.pacing_target else (1.0, 0.8, 1.2, 0.9),
            transitions=("fade", "cut", "cross_dissolve"),
            valence_curve=tuple(v for v, a in intent.emotional_curve) if intent.emotional_curve else (0.5, 0.7, 0.3, 0.8),
            arousal_curve=tuple(a for v, a in intent.emotional_curve) if intent.emotional_curve else (0.4, 0.6, 0.8, 0.5),
            render_config={"engine": "SME", "quality": "high"},
        )

    def to_dict(self) -> dict[str, Any]:
        def to_native(v):
            if isinstance(v, (np.integer,)):
                return int(v)
            if isinstance(v, (np.floating,)):
                return float(v)
            if isinstance(v, (np.ndarray,)):
                return v.tolist()
            if isinstance(v, (tuple, list)):
                return [to_native(x) for x in v]
            if isinstance(v, dict):
                return {k: to_native(v2) for k, v2 in v.items()}
            return v

        return to_native({
            "weights": self.weights,
            "mutation_scale": self.mutation_scale,
            "lineage_id": self.lineage_id,
            "age": self.age,
            "topology": self.topology,
            "arenas": list(self.arenas),
            "symbols": list(self.symbols),
            "motifs": list(self.motifs),
            "roles": list(self.roles),
            "pacing": list(self.pacing),
            "transitions": list(self.transitions),
            "valence_curve": list(self.valence_curve),
            "arousal_curve": list(self.arousal_curve),
            "render_config": self.render_config,
        })

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "ConstitutionalGenome":
        return cls(
            weights=data.get("weights", []),
            mutation_scale=data.get("mutation_scale", 0.1),
            lineage_id=data.get("lineage_id", str(uuid.uuid4())[:8]),
            age=data.get("age", 0),
            topology=data.get("topology", {}),
            arenas=tuple(data.get("arenas", ())),
            symbols=tuple(data.get("symbols", ())),
            motifs=tuple(data.get("motifs", ())),
            roles=tuple(data.get("roles", ())),
            pacing=tuple(data.get("pacing", ())),
            transitions=tuple(data.get("transitions", ())),
            valence_curve=tuple(data.get("valence_curve", ())),
            arousal_curve=tuple(data.get("arousal_curve", ())),
            render_config=data.get("render_config", {}),
        )


@dataclass(frozen=True, slots=True)
class EvidenceRecord(ConfigBase):
    CONFIG_TYPE = "evidence_record"
    id: str = field(default_factory=lambda: str(uuid.uuid4())[:12])
    genome_id: str = ""
    conformance_score: float = 0.0
    nfc_narrative_score: float = 0.0
    merkle_root: str = ""
    replay_token: str = ""
    resource_profile: dict[str, float] = field(default_factory=dict)
    continuity_score: float = 0.0
    provenance: dict[str, Any] = field(default_factory=dict)
    timestamp: str = field(default_factory=lambda: datetime.now(UTC).isoformat())

    def compute_fitness_receipt(self) -> dict[str, float]:
        return {
            "conformance": self.conformance_score,
            "narrative": self.nfc_narrative_score,
            "continuity": self.continuity_score,
            "resource_efficiency": 1.0 - min(1.0, self.resource_profile.get("compute_cost", 0.5)),
            "evidence_strength": min(1.0, (self.conformance_score + self.nfc_narrative_score) / 2.0),
        }

    def overall_fitness(self, lineage_penalty: float = 0.0) -> float:
        receipt = self.compute_fitness_receipt()
        base = sum(receipt.values()) / len(receipt)
        return max(0.0, base - lineage_penalty)


@dataclass(frozen=True, slots=True)
class LineageRecord(ConfigBase):
    CONFIG_TYPE = "lineage_record"
    id: str = field(default_factory=lambda: str(uuid.uuid4())[:12])
    genome_id: str = ""
    parent_ids: tuple[str, ...] = ()
    intent_id: str = ""
    mutation_operator: MutationOperatorType = MutationOperatorType.TOPOLOGY
    mutation_params: dict[str, Any] = field(default_factory=dict)
    evidence_id: str = ""
    timestamp: str = field(default_factory=lambda: datetime.now(UTC).isoformat())
    replay_hash: str = ""

    def compute_opacity_penalty(self) -> float:
        penalty = 0.0
        if not self.evidence_id:
            penalty += 0.3
        if not self.replay_hash:
            penalty += 0.2
        if not self.parent_ids:
            penalty += 0.1
        if self.mutation_operator == MutationOperatorType.TOPOLOGY and not self.mutation_params:
            penalty += 0.1
        return min(1.0, penalty)


@dataclass(frozen=True, slots=True)
class ConstitutionalCandidate(Generic[GenomeT]):
    genome: ConstitutionalGenome
    evidence: EvidenceRecord
    lineage: LineageRecord
    fitness_receipt: dict[str, float] = field(default_factory=dict)
    overall_fitness: float = 0.0

    def to_dict(self) -> dict[str, Any]:
        return {
            "genome": self.genome.to_dict(),
            "evidence": self.evidence.to_dict() if hasattr(self.evidence, 'to_dict') else {},
            "lineage": self.lineage.to_dict() if hasattr(self.lineage, 'to_dict') else {},
            "fitness_receipt": self.fitness_receipt,
            "overall_fitness": self.overall_fitness,
        }


@dataclass(frozen=True, slots=True)
class CEPGenerationSummary:
    generation: int
    best_fitness: float
    best_fitness_receipt: dict[str, float]
    avg_fitness: float
    avg_evidence_strength: float
    archive_size: int
    promotion_counts: dict[str, int]
    stagnation: int


class MutationOperator(ABC):
    @abstractmethod
    def mutate(self, genome: ConstitutionalGenome, config: EvolutionConfig, rng: np.random.Generator) -> ConstitutionalGenome:
        pass

    @abstractmethod
    def operator_type(self) -> MutationOperatorType:
        pass

    def log_decision(self, genome: ConstitutionalGenome, params: dict[str, Any]) -> dict[str, Any]:
        return {
            "operator": self.operator_type().value,
            "genome_id": genome.lineage_id,
            "params": params,
            "timestamp": datetime.now(UTC).isoformat(),
        }


class TopologyMutateOperator(MutationOperator):
    def operator_type(self) -> MutationOperatorType:
        return MutationOperatorType.TOPOLOGY

    def mutate(self, genome: ConstitutionalGenome, config: EvolutionConfig, rng: np.random.Generator) -> ConstitutionalGenome:
        new_topology = dict(genome.topology)
        layers = list(new_topology.get("layers", [64, 32, 16]))
        if rng.random() < 0.3 and len(layers) > 1:
            idx = rng.integers(len(layers))
            layers[idx] = max(8, int(layers[idx] * rng.uniform(0.5, 2.0)))
        elif rng.random() < 0.2:
            layers.append(rng.integers(8, 64))
        new_topology["layers"] = layers
        params = {"layer_changes": layers}
        return ConstitutionalGenome(
            weights=genome.weights,
            mutation_scale=genome.mutation_scale,
            lineage_id=genome.lineage_id,
            age=genome.age + 1,
            topology=new_topology,
            arenas=genome.arenas,
            symbols=genome.symbols,
            motifs=genome.motifs,
            roles=genome.roles,
            pacing=genome.pacing,
            transitions=genome.transitions,
            valence_curve=genome.valence_curve,
            arousal_curve=genome.arousal_curve,
            render_config=genome.render_config,
        )


class ArenaMutateOperator(MutationOperator):
    def operator_type(self) -> MutationOperatorType:
        return MutationOperatorType.ARENA

    def mutate(self, genome: ConstitutionalGenome, config: EvolutionConfig, rng: np.random.Generator) -> ConstitutionalGenome:
        all_arenas = ("narrative", "emotional", "structural", "visual", "audio", "interactive")
        new_arenas = list(genome.arenas)
        if rng.random() < 0.4 and len(new_arenas) > 1:
            idx = rng.integers(len(new_arenas))
            new_arenas.pop(idx)
        elif rng.random() < 0.3:
            available = [a for a in all_arenas if a not in new_arenas]
            if available:
                new_arenas.append(rng.choice(available))
        params = {"arena_changes": tuple(new_arenas)}
        return ConstitutionalGenome(
            weights=genome.weights,
            mutation_scale=genome.mutation_scale,
            lineage_id=genome.lineage_id,
            age=genome.age + 1,
            topology=genome.topology,
            arenas=tuple(new_arenas),
            symbols=genome.symbols,
            motifs=genome.motifs,
            roles=genome.roles,
            pacing=genome.pacing,
            transitions=genome.transitions,
            valence_curve=genome.valence_curve,
            arousal_curve=genome.arousal_curve,
            render_config=genome.render_config,
        )


class PacingMutateOperator(MutationOperator):
    def operator_type(self) -> MutationOperatorType:
        return MutationOperatorType.PACING

    def mutate(self, genome: ConstitutionalGenome, config: EvolutionConfig, rng: np.random.Generator) -> ConstitutionalGenome:
        new_pacing = list(genome.pacing)
        for i in range(len(new_pacing)):
            if rng.random() < 0.3:
                new_pacing[i] = max(0.1, min(3.0, new_pacing[i] * rng.uniform(0.7, 1.4)))
        params = {"pacing_changes": tuple(new_pacing)}
        return ConstitutionalGenome(
            weights=genome.weights,
            mutation_scale=genome.mutation_scale,
            lineage_id=genome.lineage_id,
            age=genome.age + 1,
            topology=genome.topology,
            arenas=genome.arenas,
            symbols=genome.symbols,
            motifs=genome.motifs,
            roles=genome.roles,
            pacing=tuple(new_pacing),
            transitions=genome.transitions,
            valence_curve=genome.valence_curve,
            arousal_curve=genome.arousal_curve,
            render_config=genome.render_config,
        )


class MotifMutateOperator(MutationOperator):
    def operator_type(self) -> MutationOperatorType:
        return MutationOperatorType.MOTIF

    def mutate(self, genome: ConstitutionalGenome, config: EvolutionConfig, rng: np.random.Generator) -> ConstitutionalGenome:
        new_motifs = list(genome.motifs)
        if rng.random() < 0.4 and new_motifs:
            idx = rng.integers(len(new_motifs))
            new_motifs[idx] = f"{new_motifs[idx]}_variant"
        elif rng.random() < 0.3:
            new_motifs.append(f"emergent_{rng.integers(1000)}")
        params = {"motif_changes": tuple(new_motifs)}
        return ConstitutionalGenome(
            weights=genome.weights,
            mutation_scale=genome.mutation_scale,
            lineage_id=genome.lineage_id,
            age=genome.age + 1,
            topology=genome.topology,
            arenas=genome.arenas,
            symbols=genome.symbols,
            motifs=tuple(new_motifs),
            roles=genome.roles,
            pacing=genome.pacing,
            transitions=genome.transitions,
            valence_curve=genome.valence_curve,
            arousal_curve=genome.arousal_curve,
            render_config=genome.render_config,
        )


class EmotionMutateOperator(MutationOperator):
    def operator_type(self) -> MutationOperatorType:
        return MutationOperatorType.EMOTION

    def mutate(self, genome: ConstitutionalGenome, config: EvolutionConfig, rng: np.random.Generator) -> ConstitutionalGenome:
        new_valence = list(genome.valence_curve)
        new_arousal = list(genome.arousal_curve)
        for i in range(min(len(new_valence), len(new_arousal))):
            if rng.random() < 0.3:
                new_valence[i] = max(-1.0, min(1.0, new_valence[i] + rng.normal(0, 0.2)))
                new_arousal[i] = max(0.0, min(1.0, new_arousal[i] + rng.normal(0, 0.2)))
        params = {"valence_curve": tuple(new_valence), "arousal_curve": tuple(new_arousal)}
        return ConstitutionalGenome(
            weights=genome.weights,
            mutation_scale=genome.mutation_scale,
            lineage_id=genome.lineage_id,
            age=genome.age + 1,
            topology=genome.topology,
            arenas=genome.arenas,
            symbols=genome.symbols,
            motifs=genome.motifs,
            roles=genome.roles,
            pacing=genome.pacing,
            transitions=genome.transitions,
            valence_curve=tuple(new_valence),
            arousal_curve=tuple(new_arousal),
            render_config=genome.render_config,
        )


MUTATION_OPERATORS: dict[MutationOperatorType, MutationOperator] = {
    MutationOperatorType.TOPOLOGY: TopologyMutateOperator(),
    MutationOperatorType.ARENA: ArenaMutateOperator(),
    MutationOperatorType.PACING: PacingMutateOperator(),
    MutationOperatorType.MOTIF: MotifMutateOperator(),
    MutationOperatorType.EMOTION: EmotionMutateOperator(),
}


@dataclass(frozen=True, slots=True)
class PromotionRecord(ConfigBase):
    CONFIG_TYPE = "promotion_record"
    genome_id: str = ""
    from_tier: PromotionTier = PromotionTier.SUBSTRATION
    to_tier: PromotionTier = PromotionTier.SUBSTRATE
    evidence_id: str = ""
    lineage_id: str = ""
    justification: str = ""
    timestamp: str = field(default_factory=lambda: datetime.now(UTC).isoformat())


class RMLCMetaLearner:
    def __init__(self, config: EvolutionConfig | None = None):
        self.intent_genome_fitness: dict[str, list[tuple[str, float]]] = {}
        self.mutation_outcomes: dict[str, list[tuple[str, float]]] = {}
        self.arena_effectiveness: dict[str, list[float]] = {}
        self.config = config or EvolutionConfig()

    def record(self, intent_id: str, genome_id: str, fitness: float, mutation: MutationOperatorType | None = None, arenas: tuple[str, ...] = ()) -> None:
        key = f"{intent_id}:{genome_id}"
        if key not in self.intent_genome_fitness:
            self.intent_genome_fitness[key] = []
        self.intent_genome_fitness[key].append((genome_id, fitness))

        if mutation:
            mut_key = f"{mutation.value}:{intent_id}"
            if mut_key not in self.mutation_outcomes:
                self.mutation_outcomes[mut_key] = []
            self.mutation_outcomes[mut_key].append((genome_id, fitness))

        for arena in arenas:
            if arena not in self.arena_effectiveness:
                self.arena_effectiveness[arena] = []
            self.arena_effectiveness[arena].append(fitness)

    def recommend_mutations(self, intent_id: str, top_k: int = 3) -> list[MutationOperatorType]:
        scores: dict[MutationOperatorType, float] = {}
        for mut_type in MutationOperatorType:
            key = f"{mut_type.value}:{intent_id}"
            if key in self.mutation_outcomes:
                outcomes = self.mutation_outcomes[key]
                if outcomes:
                    scores[mut_type] = np.mean([f for _, f in outcomes])
        return sorted(scores.keys(), key=lambda m: scores[m], reverse=True)[:top_k]

    def recommend_arenas(self, intent_id: str, top_k: int = 3) -> list[str]:
        scores: dict[str, float] = {}
        for arena, fitnesses in self.arena_effectiveness.items():
            if fitnesses:
                scores[arena] = np.mean(fitnesses)
        return sorted(scores.keys(), key=lambda a: scores[a], reverse=True)[:top_k]


class CEPForgeEvaluator:
    def __init__(self, config: EvolutionConfig | None = None):
        self.config = config or EvolutionConfig()

    def evaluate(self, genome: ConstitutionalGenome, intent: IntentPattern) -> EvidenceRecord:
        conformance = self._check_cems_conformance(genome, intent)
        nfc_score = self._evaluate_nfc_narrative(genome, intent)
        resource_profile = self._compute_resource_profile(genome)
        continuity = self._check_continuity(genome, intent)
        merkle = self._compute_merkle_root(genome)
        replay = self._generate_replay_token(genome, intent)

        return EvidenceRecord(
            genome_id=genome.lineage_id,
            conformance_score=conformance,
            nfc_narrative_score=nfc_score,
            merkle_root=merkle,
            replay_token=replay,
            resource_profile=resource_profile,
            continuity_score=continuity,
            provenance={
                "intent_id": intent.id,
                "genome_topology": genome.topology,
                "genome_arenas": list(genome.arenas),
            },
        )

    def _check_cems_conformance(self, genome: ConstitutionalGenome, intent: IntentPattern) -> float:
        score = 0.0
        if genome.motifs and intent.motifs:
            overlap = set(genome.motifs) & set(intent.motifs)
            score += len(overlap) / max(1, len(intent.motifs)) * 0.4
        if genome.valence_curve and intent.emotional_curve:
            target_valence = tuple(v for v, a in intent.emotional_curve)
            if target_valence:
                diff = sum(abs(a - b) for a, b in zip(genome.valence_curve, target_valence)) / len(target_valence)
                score += max(0, 1.0 - diff) * 0.3
        if genome.pacing and intent.pacing_target:
            diff = sum(abs(a - b) for a, b in zip(genome.pacing, intent.pacing_target)) / max(1, len(intent.pacing_target))
            score += max(0, 1.0 - diff) * 0.3
        return min(1.0, score)

    def _evaluate_nfc_narrative(self, genome: ConstitutionalGenome, intent: IntentPattern) -> float:
        score = 0.5
        if genome.symbols:
            score += min(0.3, len(genome.symbols) * 0.05)
        if genome.roles:
            score += min(0.2, len(genome.roles) * 0.05)
        return min(1.0, score)

    def _compute_resource_profile(self, genome: ConstitutionalGenome) -> dict[str, float]:
        layers = genome.topology.get("layers", [64, 32, 16])
        param_count = sum(layers[i] * layers[i+1] for i in range(len(layers)-1))
        return {
            "parameter_count": float(param_count),
            "compute_cost": min(1.0, param_count / 10000.0),
            "memory_mb": param_count * 4 / 1024 / 1024,
        }

    def _check_continuity(self, genome: ConstitutionalGenome, intent: IntentPattern) -> float:
        return 0.7

    def _compute_merkle_root(self, genome: ConstitutionalGenome) -> str:
        data = json.dumps(genome.to_dict(), sort_keys=True).encode()
        return hashlib.sha256(data).hexdigest()[:16]

    def _generate_replay_token(self, genome: ConstitutionalGenome, intent: IntentPattern) -> str:
        data = f"{intent.id}:{genome.lineage_id}:{genome.age}".encode()
        return hashlib.sha256(data).hexdigest()[:12]


class ConstitutionalSelection:
    def __init__(self, config: EvolutionConfig | None = None):
        self.config = config or EvolutionConfig()

    def select(self, candidates: List[ConstitutionalCandidate], rng: np.random.Generator) -> List[ConstitutionalCandidate]:
        scored = []
        for c in candidates:
            lineage_penalty = c.lineage.compute_opacity_penalty()
            overall = c.evidence.overall_fitness(lineage_penalty)
            receipt = c.evidence.compute_fitness_receipt()
            receipt["lineage_penalty"] = lineage_penalty
            scored.append(ConstitutionalCandidate(
                genome=c.genome,
                evidence=c.evidence,
                lineage=c.lineage,
                fitness_receipt=receipt,
                overall_fitness=overall,
            ))

        scored.sort(key=lambda c: c.overall_fitness, reverse=True)
        return scored

    def tournament_select(self, candidates: List[ConstitutionalCandidate], k: int, rng: np.random.Generator) -> ConstitutionalCandidate:
        competitors = rng.choice(candidates, size=min(k, len(candidates)), replace=False)
        return max(competitors, key=lambda c: c.overall_fitness)


class CEPEvolutionEngine(EvolutionEngine[ConstitutionalGenome, ConstitutionalGenome]):
    def __init__(
        self,
        config: EvolutionConfig,
        task: Task,
        archive: Archive,
        intent: IntentPattern,
        rng: np.random.Generator | None = None,
    ) -> None:
        self.config = config
        self.task = task
        self.archive = archive
        self.intent = intent
        self.rng = rng or np.random.default_rng(config.seed if config.seed else np.random.SeedSequence().entropy)
        self.rmlc = RMLCMetaLearner(config)
        self.forge = CEPForgeEvaluator(config)
        self.selection = ConstitutionalSelection(config)
        self.mutation_operators = MUTATION_OPERATORS
        self.promotion_tiers: dict[PromotionTier, list[ConstitutionalGenome]] = {
            PromotionTier.SUBSTRATION: [],
            PromotionTier.SUBSTRATE: [],
            PromotionTier.PROMOTION: [],
        }
        self.promotion_records: list[PromotionRecord] = []
        self._candidates: list[ConstitutionalCandidate] = []
        self._best_fitness: float = float("-inf")
        self._stagnation: int = 0

    def _initial_population(self) -> List[ConstitutionalGenome]:
        return [ConstitutionalGenome.from_intent(self.intent, self.rng) for _ in range(self.config.population_size)]

    def _evaluate_population(self, population: List[ConstitutionalGenome]) -> List[ConstitutionalCandidate]:
        candidates = []
        for genome in population:
            evidence = self.forge.evaluate(genome, self.intent)
            lineage = LineageRecord(
                genome_id=genome.lineage_id,
                parent_ids=(),
                intent_id=self.intent.id,
                mutation_operator=MutationOperatorType.TOPOLOGY,
                mutation_params={},
                evidence_id=evidence.id,
                replay_hash=evidence.replay_token,
            )
            receipt = evidence.compute_fitness_receipt()
            lineage_penalty = lineage.compute_opacity_penalty()
            overall = evidence.overall_fitness(lineage_penalty)
            receipt["lineage_penalty"] = lineage_penalty
            candidates.append(ConstitutionalCandidate(
                genome=genome,
                evidence=evidence,
                lineage=lineage,
                fitness_receipt=receipt,
                overall_fitness=overall,
            ))
            # Add to substration tier for promotion tracking
            if genome not in self.promotion_tiers[PromotionTier.SUBSTRATION]:
                self.promotion_tiers[PromotionTier.SUBSTRATION].append(genome)
            self.rmlc.record(self.intent.id, genome.lineage_id, overall, arenas=genome.arenas)
        return candidates

    def _spawn_next_population(self, candidates: List[ConstitutionalCandidate]) -> List[ConstitutionalGenome]:
        selected = self.selection.select(candidates, self.rng)
        next_pop: List[ConstitutionalGenome] = []

        elite_count = self.config.elite_count
        for c in selected[:elite_count]:
            next_pop.append(c.genome)

        target_offspring = self.config.population_size - elite_count
        mut_config = self.config.to_mutation_config()

        recommended_mutations = self.rmlc.recommend_mutations(self.intent.id, top_k=3)
        recommended_arenas = self.rmlc.recommend_arenas(self.intent.id, top_k=3)

        while len(next_pop) < self.config.population_size:
            parent = self.selection.tournament_select(selected, self.config.tournament_size, self.rng).genome

            mutation_choices = list(recommended_mutations) if recommended_mutations else list(MutationOperatorType)
            idx = int(self.rng.integers(len(mutation_choices)))
            mut_type = mutation_choices[idx]
            operator = self.mutation_operators[mut_type]

            child = operator.mutate(parent, self.config, self.rng)

            lineage = LineageRecord(
                genome_id=child.lineage_id,
                parent_ids=(parent.lineage_id,),
                intent_id=self.intent.id,
                mutation_operator=mut_type,
                mutation_params=operator.log_decision(parent, {}),
                evidence_id="",
                replay_hash="",
            )
            self.rmlc.record(self.intent.id, child.lineage_id, 0.0, mutation=mut_type, arenas=child.arenas)

            next_pop.append(child)

        return next_pop[:self.config.population_size]

    def _check_promotions(self, candidates: List[ConstitutionalCandidate]) -> None:
        for c in candidates:
            if c.overall_fitness < 0.6:
                continue

            if c.genome in self.promotion_tiers[PromotionTier.SUBSTRATION]:
                if c.evidence.conformance_score > 0.7 and c.evidence.nfc_narrative_score > 0.6:
                    self._promote(c, PromotionTier.SUBSTRATION, PromotionTier.SUBSTRATE)

            if c.genome in self.promotion_tiers[PromotionTier.SUBSTRATE]:
                if c.evidence.conformance_score > 0.85 and c.evidence.nfc_narrative_score > 0.8:
                    self._promote(c, PromotionTier.SUBSTRATE, PromotionTier.PROMOTION)

    def _promote(self, candidate: ConstitutionalCandidate, from_tier: PromotionTier, to_tier: PromotionTier) -> None:
        if candidate.genome in self.promotion_tiers[from_tier]:
            self.promotion_tiers[from_tier].remove(candidate.genome)
        self.promotion_tiers[to_tier].append(candidate.genome)

        record = PromotionRecord(
            genome_id=candidate.genome.lineage_id,
            from_tier=from_tier,
            to_tier=to_tier,
            evidence_id=candidate.evidence.id,
            lineage_id=candidate.lineage.id,
            justification=f"Conformance: {candidate.evidence.conformance_score:.2f}, NFC: {candidate.evidence.nfc_narrative_score:.2f}",
        )
        self.promotion_records.append(record)

    def run(
        self,
        progress_callback: Callable[[CEPGenerationSummary], None] | None = None,
    ) -> EvolutionResult[ConstitutionalGenome]:
        population = self._initial_population()

        for gen in self.promotion_tiers:
            self.promotion_tiers[gen] = []

        for generation in range(self.config.generations):
            candidates = self._evaluate_population(population)
            self._candidates = candidates

            best = max(candidates, key=lambda c: c.overall_fitness)
            if best.overall_fitness > self._best_fitness:
                self._best_fitness = best.overall_fitness
                self._stagnation = 0
            else:
                self._stagnation += 1

            self._check_promotions(candidates)

            if self._stagnation >= self.config.stagnation_limit:
                diversity_count = self.config.diversity_injection_count
                for _ in range(diversity_count):
                    population.append(ConstitutionalGenome.from_intent(self.intent, self.rng))
                self._stagnation = 0

            if progress_callback:
                avg_fit = sum(c.overall_fitness for c in candidates) / len(candidates)
                avg_evidence = sum(c.evidence.compute_fitness_receipt().get("evidence_strength", 0) for c in candidates) / len(candidates)
                promo_counts = {tier.value: len(genomes) for tier, genomes in self.promotion_tiers.items()}
                summary = CEPGenerationSummary(
                    generation=generation,
                    best_fitness=best.overall_fitness,
                    best_fitness_receipt=best.fitness_receipt,
                    avg_fitness=avg_fit,
                    avg_evidence_strength=avg_evidence,
                    archive_size=sum(len(g) for g in self.promotion_tiers.values()),
                    promotion_counts=promo_counts,
                    stagnation=self._stagnation,
                )
                progress_callback(summary)

            population = self._spawn_next_population(candidates)

        best_overall = max(self._candidates, key=lambda c: c.overall_fitness) if self._candidates else None

        hall_of_fame = []
        for tier in [PromotionTier.PROMOTION, PromotionTier.SUBSTRATE, PromotionTier.SUBSTRATION]:
            for genome in self.promotion_tiers[tier]:
                if best_overall and genome.lineage_id == best_overall.genome.lineage_id:
                    continue
                evidence = self.forge.evaluate(genome, self.intent)
                lineage = LineageRecord(genome_id=genome.lineage_id, intent_id=self.intent.id)
                receipt = evidence.compute_fitness_receipt()
                overall = evidence.overall_fitness(lineage.compute_opacity_penalty())
                hall_of_fame.append(ConstitutionalCandidate(
                    genome=genome,
                    evidence=evidence,
                    lineage=lineage,
                    fitness_receipt=receipt,
                    overall_fitness=overall,
                ))

        if best_overall:
            hall_of_fame.insert(0, best_overall)

        class CEPResult:
            def __init__(self, best: ConstitutionalCandidate, hall: list, history: list, archive: int):
                self.best = best
                self.hall_of_fame = hall
                self.history = history
                self.archive_size = archive

        return CEPResult(
            best=best_overall,
            hall=tuple(hall_of_fame),
            history=tuple([]),
            archive=sum(len(g) for g in self.promotion_tiers.values()),
        )

    def save_result(self, path: str, result: EvolutionResult[ConstitutionalGenome]) -> None:
        from pathlib import Path
        dest = Path(path)
        dest.parent.mkdir(parents=True, exist_ok=True)
        dest.write_text(json.dumps(result.to_dict() if hasattr(result, 'to_dict') else {}, indent=2), encoding="utf-8")