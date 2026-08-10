from __future__ import annotations

from typing import Any, Callable, TypeVar
from importlib.metadata import entry_points
import logging

logger = logging.getLogger(__name__)

T = TypeVar("T")


class PluginRegistry:
    def __init__(self, entry_point_group: str) -> None:
        self._entry_point_group = entry_point_group
        self._plugins: dict[str, Callable[..., Any]] = {}
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
                    self._plugins[ep.name] = factory
                    logger.debug("Loaded plugin %s from entry point", ep.name)
                except Exception as e:
                    logger.warning("Failed to load plugin %s: %s", ep.name, e)
        except Exception as e:
            logger.debug("No entry points for group %s: %s", self._entry_point_group, e)

    def register(self, name: str, factory: Callable[..., T]) -> None:
        if name in self._plugins:
            raise ValueError(f"Plugin {name} already registered")
        self._plugins[name] = factory

    def create(self, name: str, **kwargs: Any) -> T:
        if name not in self._plugins:
            raise KeyError(f"Plugin {name} not found. Available: {list(self._plugins.keys())}")
        return self._plugins[name](**kwargs)

    def list_plugins(self) -> list[str]:
        return list(self._plugins.keys())

    def __contains__(self, name: str) -> bool:
        return name in self._plugins


# Global registries
task_registry = PluginRegistry("evolving_ai.tasks")
archive_registry = PluginRegistry("evolving_ai.archives")
engine_registry = PluginRegistry("evolving_ai.engines")
genome_registry = PluginRegistry("evolving_ai.genomes")


def register_task(name: str, factory: Callable[..., Any]) -> None:
    task_registry.register(name, factory)


def register_archive(name: str, factory: Callable[..., Any]) -> None:
    archive_registry.register(name, factory)


def register_engine(name: str, factory: Callable[..., Any]) -> None:
    engine_registry.register(name, factory)


def register_genome(name: str, factory: Callable[..., Any]) -> None:
    genome_registry.register(name, factory)