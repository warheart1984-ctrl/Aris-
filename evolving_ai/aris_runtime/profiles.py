from __future__ import annotations

from dataclasses import dataclass


DEFAULT_PROFILE_ID = "v2"


@dataclass(frozen=True, slots=True)
class ArisRuntimeProfile:
    id: str
    label: str
    system_name: str
    service_name: str
    desktop_title: str
    artifact_name: str
    data_dir_name: str
    runtime_dir_name: str
    entry_script: str

    def payload(self) -> dict[str, str]:
        return {
            "id": self.id,
            "label": self.label,
            "system_name": self.system_name,
            "service_name": self.service_name,
            "desktop_title": self.desktop_title,
            "artifact_name": self.artifact_name,
            "data_dir_name": self.data_dir_name,
            "runtime_dir_name": self.runtime_dir_name,
            "entry_script": self.entry_script,
        }


_PROFILES = {
    "v2": ArisRuntimeProfile(
        id="v2",
        label="ARIS V2",
        system_name="ARIS V2",
        service_name="Advanced Repo Intelligence Service V2",
        desktop_title="ARIS V2 Desktop",
        artifact_name="ARIS V2",
        data_dir_name="ARIS V2",
        runtime_dir_name="aris_v2",
        entry_script="desktop.py",
    ),
}


def aris_runtime_profiles() -> tuple[ArisRuntimeProfile, ...]:
    return tuple(_PROFILES.values())


def profile_choices() -> tuple[str, ...]:
    return tuple(_PROFILES.keys())


def resolve_profile(profile_id: str | None) -> ArisRuntimeProfile:
    normalized = str(profile_id or DEFAULT_PROFILE_ID).strip().lower()
    if not normalized:
        normalized = DEFAULT_PROFILE_ID
    if normalized not in _PROFILES:
        raise ValueError(f"Unknown ARIS runtime profile: {profile_id!r}")
    return _PROFILES[normalized]
