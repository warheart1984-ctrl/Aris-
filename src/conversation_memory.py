from __future__ import annotations

import re

from .constants_runtime import ARIS_HANDBOOK_ID, UL_ROOT_LAW_ID


FOUNDATION_SHADOW_PATTERN = re.compile(
    rf"({re.escape(UL_ROOT_LAW_ID)}|{re.escape(ARIS_HANDBOOK_ID)})\s*[:=]",
    re.IGNORECASE,
)


def is_foundational_shadow_attempt(text: str) -> bool:
    return bool(FOUNDATION_SHADOW_PATTERN.search(str(text or "")))
