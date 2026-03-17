from __future__ import annotations

import unicodedata

SAFE_RULES = (
    "megnyit",
    "open",
    "nevjegy",
    "about",
    "beallitas",
    "settings",
    "inform",
    "nezet",
    "view",
)
CAUTION_RULES = (
    "import",
    "export",
    "szamitas",
    "calculate",
    "projektvalt",
    "project switch",
)
BLOCKED_RULES = (
    "kilep",
    "exit",
    "torles",
    "delete",
    "reset",
    "feluli",
    "overwrite",
    "bezar",
    "close",
)


def normalize_menu_text(text: str) -> str:
    raw = (text or "").strip().lower()
    normalized = unicodedata.normalize("NFKD", raw)
    return "".join(ch for ch in normalized if not unicodedata.combining(ch))


def classify_safety(menu_path: list[str]) -> str:
    joined = " > ".join(normalize_menu_text(part) for part in menu_path)
    if any(rule in joined for rule in BLOCKED_RULES):
        return "blocked"
    if any(rule in joined for rule in CAUTION_RULES):
        return "caution"
    if any(rule in joined for rule in SAFE_RULES):
        return "safe"
    return "caution"


def is_action_allowed(menu_path: list[str], mode: str = "safe") -> bool:
    levels = {"safe": 0, "hybrid": 1, "caution": 1, "blocked": 2}
    target = classify_safety(menu_path)
    current_level = levels.get(mode, 0)
    return levels.get(target, 2) <= current_level
