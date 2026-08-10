from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from enum import Enum, auto
from typing import Any, Dict, List, Optional, Set, Type
import uuid


class Law(Enum):
    """Individual constitutional laws for evolutionary engines."""
    DETERMINISM = auto()
    ELITISM = auto()
    POPULATION_INVARIANCE = auto()
    ARCHIVE_MONOTONICITY = auto()
    SELECTION_MONOTONICITY = auto()
    OPTIMIZATION_PRESSURE = auto()
    SEMANTIC_EQUIVALENCE = auto()


@dataclass(frozen=True, slots=True)
class LawDefinition:
    law: Law
    name: str
    description: str
    mandatory_in_base: bool = False


LAW_REGISTRY: Dict[Law, LawDefinition] = {
    Law.DETERMINISM: LawDefinition(
        law=Law.DETERMINISM,
        name="Determinism",
        description="Same seed + same initial population → identical trajectory",
        mandatory_in_base=False,
    ),
    Law.ELITISM: LawDefinition(
        law=Law.ELITISM,
        name="Elitism",
        description="Best fitness never decreases across generations (total preorder)",
        mandatory_in_base=False,
    ),
    Law.POPULATION_INVARIANCE: LawDefinition(
        law=Law.POPULATION_INVARIANCE,
        name="Population Invariance",
        description="Population size constant per generation",
        mandatory_in_base=True,
    ),
    Law.ARCHIVE_MONOTONICITY: LawDefinition(
        law=Law.ARCHIVE_MONOTONICITY,
        name="Archive Monotonicity",
        description="Archive size never decreases",
        mandatory_in_base=False,
    ),
Law.SELECTION_MONOTONICITY: LawDefinition(
        law=Law.SELECTION_MONOTONICITY,
        name="Selection Monotonicity",
        description="E[offspring score] >= E[parent score] under selection distribution",
        mandatory_in_base=False,
    ),
    Law.OPTIMIZATION_PRESSURE: LawDefinition(
        law=Law.OPTIMIZATION_PRESSURE,
        name="Optimization Pressure Declaration",
        description="Every evolutionary profile must declare its optimization pressure. The selection mechanism must favor that declared pressure in expectation. Conformance verifies the selection distribution improves the declared pressure.",
        mandatory_in_base=False,
    ),
    Law.SEMANTIC_EQUIVALENCE: LawDefinition(
        law=Law.SEMANTIC_EQUIVALENCE,
        name="Semantic Equivalence",
        description="Distributed evaluation produces same evidence bundle as sequential",
        mandatory_in_base=False,
    ),
}


class ContractProfile(ABC):
    """A set of laws that an engine must satisfy."""

    def __init__(self, name: str, description: str = "") -> None:
        self.name = name
        self.description = description
        self._laws: Set[Law] = set()

    def requires(self, law: Law) -> "ContractProfile":
        self._laws.add(law)
        return self

    def laws(self) -> Set[Law]:
        return self._laws.copy()

    def satisfies(self, other: "ContractProfile") -> bool:
        """Check if this profile satisfies another (superset)."""
        return other.laws().issubset(self._laws)

    @abstractmethod
    def validate(self, evidence_bundle: "EvidenceBundle") -> Dict[Law, bool]:
        """Validate which laws are satisfied by the evidence."""
        pass

    def __repr__(self) -> str:
        law_names = [LAW_REGISTRY[l].name for l in self._laws]
        return f"{self.name}({', '.join(law_names)})"


LAW_NAME_MAP = {
    Law.DETERMINISM: "determinism",
    Law.ELITISM: "elitism",
    Law.POPULATION_INVARIANCE: "population_invariance",
    Law.ARCHIVE_MONOTONICITY: "archive_monotonicity",
    Law.SELECTION_MONOTONICITY: "selection_monotonicity",
    Law.OPTIMIZATION_PRESSURE: "optimization_pressure",
    Law.SEMANTIC_EQUIVALENCE: "semantic_equivalence",
}


def _check_law(evidence_bundle: "EvidenceBundle", law: Law) -> bool:
    name = LAW_NAME_MAP[law]
    result = next((r for r in evidence_bundle.results if r.law_name == name), None)
    return result.passed if result else False


class BaseEngineContract(ContractProfile):
    """Mandatory laws for all evolutionary engines."""
    
    def __init__(self) -> None:
        super().__init__("BaseEngineContract", "Mandatory laws for all evolutionary engines")
        for law, defn in LAW_REGISTRY.items():
            if defn.mandatory_in_base:
                self.requires(law)

    def validate(self, evidence_bundle: "EvidenceBundle") -> Dict[Law, bool]:
        return {law: _check_law(evidence_bundle, law) for law in self._laws}


class DeterministicEngineProfile(ContractProfile):
    """Engines that must be deterministic under fixed seed."""
    
    def __init__(self) -> None:
        super().__init__("DeterministicEngineProfile", "Determinism under fixed seed")
        self.requires(Law.DETERMINISM)

    def validate(self, evidence_bundle: "EvidenceBundle") -> Dict[Law, bool]:
        return {Law.DETERMINISM: _check_law(evidence_bundle, Law.DETERMINISM)}


class ElitistEngineProfile(ContractProfile):
    """Engines that preserve best fitness (non-decreasing)."""
    
    def __init__(self) -> None:
        super().__init__("ElitistEngineProfile", "Elitism - best fitness non-decreasing")
        self.requires(Law.ELITISM)

    def validate(self, evidence_bundle: "EvidenceBundle") -> Dict[Law, bool]:
        return {Law.ELITISM: _check_law(evidence_bundle, Law.ELITISM)}


class ArchivePreservingProfile(ContractProfile):
    """Engines with append-only archive."""
    
    def __init__(self) -> None:
        super().__init__("ArchivePreservingProfile", "Archive monotonicity")
        self.requires(Law.ARCHIVE_MONOTONICITY)

    def validate(self, evidence_bundle: "EvidenceBundle") -> Dict[Law, bool]:
        return {Law.ARCHIVE_MONOTONICITY: _check_law(evidence_bundle, Law.ARCHIVE_MONOTONICITY)}


class DistributedEngineProfile(ContractProfile):
    """Engines with distributed evaluation semantic equivalence."""
    
    def __init__(self) -> None:
        super().__init__("DistributedEngineProfile", "Semantic equivalence between distributed and sequential")
        self.requires(Law.SEMANTIC_EQUIVALENCE)

    def validate(self, evidence_bundle: "EvidenceBundle") -> Dict[Law, bool]:
        return {Law.SEMANTIC_EQUIVALENCE: _check_law(evidence_bundle, Law.SEMANTIC_EQUIVALENCE)}


class StochasticExplorationProfile(ContractProfile):
    """Engines that intentionally allow selection non-monotonicity for exploration."""
    
    def __init__(self) -> None:
        super().__init__("StochasticExplorationProfile", "Allows non-monotonic selection for diversity")
        # Explicitly does NOT require SELECTION_MONOTONICITY


# Predefined composite profiles
class StandardEvolutionaryProfile(ContractProfile):
    """Standard evolutionary engine: deterministic, elitist, archive-preserving, fitness-selective."""
    
    def __init__(self) -> None:
        super().__init__("StandardEvolutionaryProfile", "Deterministic + Elitist + Archive-Preserving + Fitness-Selective")
        self.requires(Law.DETERMINISM)
        self.requires(Law.ELITISM)
        self.requires(Law.POPULATION_INVARIANCE)
        self.requires(Law.ARCHIVE_MONOTONICITY)
        self.requires(Law.OPTIMIZATION_PRESSURE)

    def validate(self, evidence_bundle: "EvidenceBundle") -> Dict[Law, bool]:
        return {law: _check_law(evidence_bundle, law) for law in self._laws}


class CMAESProfile(ContractProfile):
    """CMA-ES engine: deterministic, elitist, archive-preserving, fitness-selective."""
    
    def __init__(self) -> None:
        super().__init__("CMAESProfile", "CMA-ES: Deterministic + Elitist + Archive-Preserving + Fitness-Selective")
        self.requires(Law.DETERMINISM)
        self.requires(Law.ELITISM)
        self.requires(Law.POPULATION_INVARIANCE)
        self.requires(Law.ARCHIVE_MONOTONICITY)
        self.requires(Law.OPTIMIZATION_PRESSURE)
        # Explicitly NOT requiring SELECTION_MONOTONICITY

    def validate(self, evidence_bundle: "EvidenceBundle") -> Dict[Law, bool]:
        return {law: _check_law(evidence_bundle, law) for law in self._laws}


class SpeciationProfile(ContractProfile):
    """Speciation engine: deterministic, non-elitist (allows regression), archive-preserving, fitness-selective within species."""
    
    def __init__(self) -> None:
        super().__init__("SpeciationProfile", "Speciation: Deterministic + Archive-Preserving + Fitness-Selective")
        self.requires(Law.DETERMINISM)
        self.requires(Law.POPULATION_INVARIANCE)
        self.requires(Law.ARCHIVE_MONOTONICITY)
        self.requires(Law.OPTIMIZATION_PRESSURE)
        # Explicitly NOT requiring ELITISM (species can go extinct)

    def validate(self, evidence_bundle: "EvidenceBundle") -> Dict[Law, bool]:
        return {law: _check_law(evidence_bundle, law) for law in self._laws}


class MAPElitesProfile(ContractProfile):
    """MAP-Elites engine: deterministic, archive-preserving, quality-diversity focus (grid-based selection)."""
    
    def __init__(self) -> None:
        super().__init__("MAPElitesProfile", "MAP-Elites: Deterministic + Archive-Preserving (grid-based selection)")
        self.requires(Law.DETERMINISM)
        self.requires(Law.POPULATION_INVARIANCE)
        self.requires(Law.ARCHIVE_MONOTONICITY)
        # Not requiring ELITISM or OPTIMIZATION_PRESSURE (grid-based selection)

    def validate(self, evidence_bundle: "EvidenceBundle") -> Dict[Law, bool]:
        return {law: _check_law(evidence_bundle, law) for law in self._laws}


# Engine → Profile mapping
ENGINE_PROFILES: Dict[str, ContractProfile] = {
    "standard": StandardEvolutionaryProfile(),
    "cmaes": CMAESProfile(),
    "speciation": SpeciationProfile(),
    "map_elites": MAPElitesProfile(),
    "nsga2": MAPElitesProfile(),  # Similar to MAP-Elites
}


def get_profile_for_engine(engine_name: str) -> Optional[ContractProfile]:
    return ENGINE_PROFILES.get(engine_name)


def list_available_profiles() -> List[ContractProfile]:
    return list(ENGINE_PROFILES.values())