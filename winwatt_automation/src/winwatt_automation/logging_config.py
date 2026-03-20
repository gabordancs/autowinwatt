from __future__ import annotations

from loguru import logger


def configure_logging(*, level: str = "INFO", log_profile: str = "concise") -> int:
    resolved_profile = str(log_profile or "concise").strip().lower()
    sink_level = "DEBUG" if resolved_profile == "diagnostic" else level
    logger.remove()
    return logger.add(lambda msg: print(msg, end=""), level=sink_level)
