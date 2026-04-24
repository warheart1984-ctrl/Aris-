from __future__ import annotations

from collections import OrderedDict
from dataclasses import dataclass, field
from typing import Generic, TypeVar

T = TypeVar("T")


@dataclass(slots=True)
class LruCache(Generic[T]):
    capacity: int
    _items: OrderedDict[str, T] = field(default_factory=OrderedDict)

    def get(self, key: str) -> T | None:
        if key not in self._items:
            return None
        value = self._items.pop(key)
        self._items[key] = value
        return value

    def put(self, key: str, value: T) -> None:
        if key in self._items:
            self._items.pop(key)
        self._items[key] = value
        while len(self._items) > self.capacity:
            self._items.popitem(last=False)

    def size(self) -> int:
        return len(self._items)
