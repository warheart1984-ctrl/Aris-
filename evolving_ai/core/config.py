from __future__ import annotations

from dataclasses import dataclass, field, fields, is_dataclass
from pathlib import Path
from typing import Any, ClassVar, TypeVar, get_type_hints
import json
import yaml

T = TypeVar("T", bound="ConfigBase")


class ConfigBase:
    _registry: ClassVar[dict[str, type["ConfigBase"]]] = {}
    _discriminator: ClassVar[str] = "type"

    def __init_subclass__(cls, **kwargs: Any) -> None:
        super().__init_subclass__(**kwargs)
        if hasattr(cls, "CONFIG_TYPE"):
            ConfigBase._registry[cls.CONFIG_TYPE] = cls

    @classmethod
    def register_subtype(cls, subtype: type["ConfigBase"]) -> None:
        if not hasattr(subtype, "CONFIG_TYPE"):
            raise ValueError(f"{subtype} must have CONFIG_TYPE class attribute")
        ConfigBase._registry[subtype.CONFIG_TYPE] = subtype

    @classmethod
    def from_dict(cls: type[T], data: dict[str, Any]) -> T:
        if cls._discriminator in data:
            type_name = data.pop(cls._discriminator)
            if type_name not in cls._registry:
                raise ValueError(f"Unknown config type: {type_name}. Registered: {list(cls._registry.keys())}")
            return cls._registry[type_name].from_dict(data)
        return cls._from_dict(data)

    @classmethod
    def _from_dict(cls: type[T], data: dict[str, Any]) -> T:
        field_types = get_type_hints(cls)
        kwargs = {}
        for f in fields(cls):
            if f.name in data:
                value = data[f.name]
                ftype = field_types.get(f.name, Any)
                if is_dataclass(ftype) and issubclass(ftype, ConfigBase) and isinstance(value, dict):
                    kwargs[f.name] = ftype.from_dict(value)
                elif hasattr(ftype, "__origin__") and ftype.__origin__ is list:
                    item_type = ftype.__args__[0] if ftype.__args__ else Any
                    if is_dataclass(item_type) and issubclass(item_type, ConfigBase):
                        kwargs[f.name] = [item_type.from_dict(v) if isinstance(v, dict) else v for v in value]
                    else:
                        kwargs[f.name] = value
                else:
                    kwargs[f.name] = value
        return cls(**kwargs)

    def to_dict(self, include_type: bool = True) -> dict[str, Any]:
        result = {}
        if include_type and hasattr(self, "CONFIG_TYPE"):
            result[self._discriminator] = self.CONFIG_TYPE
        for f in fields(self):
            value = getattr(self, f.name)
            if is_dataclass(value) and isinstance(value, ConfigBase):
                result[f.name] = value.to_dict(include_type=True)
            elif isinstance(value, list) and value and is_dataclass(value[0]) and isinstance(value[0], ConfigBase):
                result[f.name] = [v.to_dict(include_type=True) for v in value]
            else:
                result[f.name] = value
        return result

    @classmethod
    def from_yaml(cls: type[T], path: str | Path) -> T:
        path = Path(path)
        with path.open("r") as f:
            data = yaml.safe_load(f)
        return cls.from_dict(data)

    @classmethod
    def from_json(cls: type[T], path: str | Path) -> T:
        path = Path(path)
        with path.open("r") as f:
            data = json.load(f)
        return cls.from_dict(data)

    def to_yaml(self, path: str | Path) -> None:
        path = Path(path)
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open("w") as f:
            yaml.dump(self.to_dict(), f, default_flow_style=False, sort_keys=False)

    def to_json(self, path: str | Path) -> None:
        path = Path(path)
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open("w") as f:
            json.dump(self.to_dict(), f, indent=2)


@dataclass
class EvolutionConfig(ConfigBase):
    CONFIG_TYPE = "evolution"
    population_size: int = 96
    generations: int = 80
    mutation_rate: float = 0.18
    novelty_weight: float = 0.25
    elite_fraction: float = 0.05
    tournament_size: int = 4
    seed: int | None = None


@dataclass
class TaskConfig(ConfigBase):
    CONFIG_TYPE = "task"
    name: str = "xor"
    hidden_layers: tuple[int, ...] = (6, 6)


@dataclass
class ArchiveConfig(ConfigBase):
    CONFIG_TYPE = "archive"
    type: str = "novelty"
    k: int = 15
    grid_size: int = 10


@dataclass
class ExperimentConfig(ConfigBase):
    CONFIG_TYPE = "experiment"
    evolution: EvolutionConfig = field(default_factory=EvolutionConfig)
    task: TaskConfig = field(default_factory=TaskConfig)
    archive: ArchiveConfig = field(default_factory=ArchiveConfig)

    @classmethod
    def from_yaml(cls, path: str | Path) -> "ExperimentConfig":
        return super().from_yaml(path)

    @classmethod
    def from_json(cls, path: str | Path) -> "ExperimentConfig":
        return super().from_json(path)