from __future__ import annotations

import re


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
    return clean_menu_title(title).lower()


def menu_titles_equal(a: str, b: str) -> bool:
    return normalize_menu_title(a) == normalize_menu_title(b)

