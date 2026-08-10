from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field, fields, is_dataclass
from pathlib import Path
from typing import Any, ClassVar, Generic, Literal, TypeVar, get_type_hints
import json
import yaml

T = TypeVar("T", bound="ConfigBase")


class ConfigBase(ABC):
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
            elif f.default is not field() and f.default_factory is not field():
                pass
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


ActivationName = Literal["relu", "sigmoid", "tanh"]


@dataclass(frozen=True, slots=True)
class NetworkShape:
    input_size: int
    hidden_layers: tuple[int, ...]
    output_size: int
    activation: ActivationName = "tanh"
    output_activation: ActivationName = "sigmoid"

    def __post_init__(self) -> None:
        layer_sizes = (self.input_size, *self.hidden_layers, self.output_size)
        if any(size <= 0 for size in layer_sizes):
            raise ValueError("All layer sizes must be positive integers.")

    @property
    def layer_sizes(self) -> tuple[int, ...]:
        return (self.input_size, *self.hidden_layers, self.output_size)

    @property
    def parameter_count(self) -> int:
        total = 0
        for input_width, output_width in zip(self.layer_sizes, self.layer_sizes[1:]):
            total += (input_width * output_width) + output_width
        return total