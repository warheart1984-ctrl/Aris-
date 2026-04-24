__all__ = ["ArisRuntime", "ArisChatService"]


def __getattr__(name: str):
    if name == "ArisRuntime":
        from .runtime import ArisRuntime

        return ArisRuntime
    if name == "ArisChatService":
        from .service import ArisChatService

        return ArisChatService
    raise AttributeError(name)
