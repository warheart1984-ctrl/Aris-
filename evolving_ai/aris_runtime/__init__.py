__all__ = [
    "ArisV2Runtime",
    "ArisRuntimeChatService",
    "ArisRuntimeDesktopHost",
]


def __getattr__(name: str):
    if name == "ArisV2Runtime":
        from .runtime import ArisV2Runtime

        return ArisV2Runtime
    if name == "ArisRuntimeChatService":
        from .service import ArisRuntimeChatService

        return ArisRuntimeChatService
    if name == "ArisRuntimeDesktopHost":
        from .desktop_support import ArisRuntimeDesktopHost

        return ArisRuntimeDesktopHost
    raise AttributeError(name)
