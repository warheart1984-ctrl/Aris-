from __future__ import annotations

from collections.abc import Callable
from functools import wraps


def law_wrapped(*, engine_attr: str = "runtime_law", actor: str, route_name: str) -> Callable:
    def decorator(func: Callable) -> Callable:
        @wraps(func)
        def wrapper(self, *args, **kwargs):
            engine = getattr(self, engine_attr)
            if hasattr(engine, "record_sensitive_entry"):
                engine.record_sensitive_entry(actor=actor, route_name=route_name)
            return func(self, *args, **kwargs)

        return wrapper

    return decorator
