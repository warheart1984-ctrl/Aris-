from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, List, Protocol, Tuple
import math


class Archive(Protocol):
    def add(self, descriptor: Any, fitness: float, genome: Any) -> None:
        ...

    def novelty(self, descriptor: Any) -> float:
        ...


@dataclass
class ArchiveEntry:
    descriptor: Any
    fitness: float
    genome: Any


@dataclass
class NoveltyArchive:
    entries: List[ArchiveEntry] = field(default_factory=list)
    k: int = 15

    def add(self, descriptor: Any, fitness: float, genome: Any) -> None:
        self.entries.append(ArchiveEntry(descriptor, fitness, genome))

    def novelty(self, descriptor: Any) -> float:
        if not self.entries:
            return 0.0
        dists = []
        for e in self.entries:
            d = self._distance(descriptor, e.descriptor)
            dists.append(d)
        dists.sort()
        k = min(self.k, len(dists))
        return sum(dists[:k]) / float(k)

    def _distance(self, a: Any, b: Any) -> float:
        if isinstance(a, tuple) and isinstance(b, tuple):
            return math.sqrt(sum((x - y) ** 2 for x, y in zip(a, b)))
        if isinstance(a, (int, float)) and isinstance(b, (int, float)):
            return abs(a - b)
        return 0.0


@dataclass
class MapElitesArchive:
    bins: dict = field(default_factory=dict)
    grid_size: int = 10
    feature_min: Tuple[float, ...] = (0.0, 0.0)
    feature_max: Tuple[float, ...] = (1.0, 1.0)

    def _bin_index(self, descriptor: Tuple[float, ...]) -> Tuple[int, ...]:
        idx = []
        for i, val in enumerate(descriptor):
            if self.feature_max[i] == self.feature_min[i]:
                idx.append(0)
            else:
                normalized = (val - self.feature_min[i]) / (self.feature_max[i] - self.feature_min[i])
                normalized = max(0.0, min(1.0, normalized))
                idx.append(int(normalized * (self.grid_size - 1)))
        return tuple(idx)

    def add(self, descriptor: Tuple[float, ...], fitness: float, genome: Any) -> bool:
        idx = self._bin_index(descriptor)
        if idx not in self.bins or fitness > self.bins[idx][0]:
            self.bins[idx] = (fitness, genome, descriptor)
            return True
        return False

    def get_best(self, descriptor: Tuple[float, ...]) -> Any | None:
        idx = self._bin_index(descriptor)
        return self.bins.get(idx)

    def all_elites(self) -> List[Tuple[Tuple[int, ...], float, Any, Tuple[float, ...]]]:
        return [(idx, fit, gen, desc) for idx, (fit, gen, desc) in self.bins.items()]