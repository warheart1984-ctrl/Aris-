from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from importlib.metadata import entry_points
from typing import Any, Callable, Generic, TypeVar
import logging

logger = logging.getLogger(__name__)

T = TypeVar("T")


@dataclass(frozen=True, slots=True)
class PluginSpec(Generic[T]):
    name: str
    factory: Callable[..., T]
    metadata: dict[str, Any] = field(default_factory=dict)


class PluginRegistry(Generic[T]):
    def __init__(self, interface: type[T], entry_point_group: str) -> None:
        self._interface = interface
        self._entry_point_group = entry_point_group
        self._plugins: dict[str, PluginSpec[T]] = {}
        self._load_entry_points()

    def _load_entry_points(self) -> None:
        try:
            eps = entry_points(group=self._entry_point_group)
            for ep in eps:
                try:
                    factory = ep.load()
                    if not callable(factory):
                        logger.warning("Entry point %s is not callable", ep.name)
                        continue
                    self._plugins[ep.name] = PluginSpec(name=ep.name, factory=factory)
                    logger.debug("Loaded plugin %s from entry point", ep.name)
                except Exception as e:
                    logger.warning("Failed to load plugin %s: %s", ep.name, e)
        except Exception as e:
            logger.debug("No entry points for group %s: %s", self._entry_point_group, e)

    def register(self, name: str, factory: Callable[..., T], metadata: dict[str, Any] | None = None) -> None:
        if name in self._plugins:
            raise ValueError(f"Plugin {name} already registered")
        self._plugins[name] = PluginSpec(name=name, factory=factory, metadata=metadata or {})

    def create(self, name: str, **kwargs: Any) -> T:
        if name not in self._plugins:
            raise KeyError(f"Plugin {name} not found. Available: {list(self._plugins.keys())}")
        return self._plugins[name].factory(**kwargs)

    def get_spec(self, name: str) -> PluginSpec[T]:
        return self._plugins[name]

    def list_plugins(self) -> list[str]:
        return list(self._plugins.keys())

    def __contains__(self, name: str) -> bool:
        return name in self._plugins


def create_registry(interface: type[T], entry_point_group: str) -> PluginRegistry[T]:
    return PluginRegistry(interface, entry_point_group)