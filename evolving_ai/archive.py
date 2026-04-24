from __future__ import annotations

from dataclasses import dataclass, field
import math


def behavior_distance(left: tuple[float, ...], right: tuple[float, ...]) -> float:
    if len(left) != len(right):
        raise ValueError("Behavior vectors must be the same length.")
    squared = [(l_value - r_value) ** 2 for l_value, r_value in zip(left, right)]
    return math.sqrt(sum(squared))


@dataclass(frozen=True, slots=True)
class ArchiveEntry:
    behavior: tuple[float, ...]
    objective_score: float
    generation: int

    def to_dict(self) -> dict[str, object]:
        return {
            "behavior": list(self.behavior),
            "objective_score": self.objective_score,
            "generation": self.generation,
        }


@dataclass(slots=True)
class NoveltyArchive:
    k_neighbors: int = 5
    entries: list[ArchiveEntry] = field(default_factory=list)

    def score(
        self,
        behavior: tuple[float, ...],
        population_behaviors: list[tuple[float, ...]],
    ) -> float:
        distances: list[float] = []
        distances.extend(
            behavior_distance(behavior, other)
            for other in population_behaviors
            if other is not behavior
        )
        distances.extend(
            behavior_distance(behavior, entry.behavior) for entry in self.entries
        )
        if not distances:
            return 0.0

        distances.sort()
        k = min(self.k_neighbors, len(distances))
        return sum(distances[:k]) / k

    def add(self, behavior: tuple[float, ...], objective_score: float, generation: int) -> None:
        self.entries.append(
            ArchiveEntry(
                behavior=behavior,
                objective_score=objective_score,
                generation=generation,
            )
        )

    def to_dict(self) -> list[dict[str, object]]:
        return [entry.to_dict() for entry in self.entries]
