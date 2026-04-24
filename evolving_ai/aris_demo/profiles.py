from __future__ import annotations

from dataclasses import dataclass


DEFAULT_PROFILE_ID = "demo"


@dataclass(frozen=True, slots=True)
class ArisDemoProfile:
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
    "demo": ArisDemoProfile(
        id="demo",
        label="ARIS Demo",
        system_name="ARIS Demo",
        service_name="Advanced Repo Intelligence Service Demo",
        desktop_title="ARIS Demo Desktop",
        artifact_name="ARIS Demo",
        data_dir_name="ARIS Demo",
        runtime_dir_name="aris_demo",
        entry_script="desktop.py",
    ),
    "v1": ArisDemoProfile(
        id="v1",
        label="ARIS Demo V1",
        system_name="ARIS Demo V1",
        service_name="Advanced Repo Intelligence Service Demo V1",
        desktop_title="ARIS Demo V1 Desktop",
        artifact_name="ARIS Demo V1",
        data_dir_name="ARIS Demo V1",
        runtime_dir_name="aris_demo_v1",
        entry_script="desktop_v1.py",
    ),
    "v2": ArisDemoProfile(
        id="v2",
        label="ARIS Demo V2",
        system_name="ARIS Demo V2",
        service_name="Advanced Repo Intelligence Service Demo V2",
        desktop_title="ARIS Demo V2 Desktop",
        artifact_name="ARIS Demo V2",
        data_dir_name="ARIS Demo V2",
        runtime_dir_name="aris_demo_v2",
        entry_script="desktop_v2.py",
    ),
}


def aris_demo_profiles() -> tuple[ArisDemoProfile, ...]:
    return tuple(_PROFILES.values())


def profile_choices() -> tuple[str, ...]:
    return tuple(_PROFILES.keys())


def resolve_profile(profile_id: str | None) -> ArisDemoProfile:
    normalized = str(profile_id or DEFAULT_PROFILE_ID).strip().lower()
    return _PROFILES.get(normalized, _PROFILES[DEFAULT_PROFILE_ID])
