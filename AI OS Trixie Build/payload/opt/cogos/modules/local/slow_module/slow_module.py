#!/usr/bin/env python3
"""Validly admitted module that intentionally exceeds the v7 sandbox timeout."""

from __future__ import annotations

import json
import time

time.sleep(10)
print(json.dumps({"module": "slow_module", "status": "late"}, sort_keys=True))
