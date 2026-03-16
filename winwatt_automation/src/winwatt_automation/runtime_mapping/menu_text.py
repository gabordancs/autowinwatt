from __future__ import annotations

import re

from loguru import logger


_WHITESPACE_RE = re.compile(r"\s+")


def clean_menu_title(title: str) -> str:
    if not title:
        return ""

    cleaned = str(title).strip().replace("&", "")
    while cleaned.endswith("...") or cleaned.endswith("…"):
        if cleaned.endswith("..."):
            cleaned = cleaned[:-3]
        elif cleaned.endswith("…"):
            cleaned = cleaned[:-1]
        cleaned = cleaned.rstrip()

    return _WHITESPACE_RE.sub(" ", cleaned).strip()


def normalize_menu_title(title: str) -> str:
    raw = str(title or "")
    normalized = clean_menu_title(raw).casefold()
    stripped = raw.strip()
    if stripped.endswith("...") or stripped.endswith("…"):
        logger.debug('normalize_menu_title ellipsis_handled raw="{}" normalized="{}"', raw, normalized)
    return normalized


def menu_titles_equal(a: str, b: str) -> bool:
    return normalize_menu_title(a) == normalize_menu_title(b)
