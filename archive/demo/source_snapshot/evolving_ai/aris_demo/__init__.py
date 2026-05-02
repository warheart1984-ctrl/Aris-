__all__ = [
    "ArisDemoRuntime",
    "ArisDemoV1Runtime",
    "ArisDemoV2Runtime",
    "ArisDemoChatService",
    "ArisDemoDesktopHost",
]


def __getattr__(name: str):
    if name == "ArisDemoRuntime":
        from .runtime import ArisDemoRuntime

        return ArisDemoRuntime
    if name == "ArisDemoV1Runtime":
        from .runtime import ArisDemoV1Runtime

        return ArisDemoV1Runtime
    if name == "ArisDemoV2Runtime":
        from .runtime import ArisDemoV2Runtime

        return ArisDemoV2Runtime
    if name == "ArisDemoChatService":
        from .service import ArisDemoChatService

        return ArisDemoChatService
    if name == "ArisDemoDesktopHost":
        from .desktop_support import ArisDemoDesktopHost

        return ArisDemoDesktopHost
    raise AttributeError(name)