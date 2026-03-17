"""Runtime mapping performance configuration."""

from __future__ import annotations

PERFORMANCE_MODE = "fast"


def is_fast_mode() -> bool:
    return PERFORMANCE_MODE.strip().lower() == "fast"

