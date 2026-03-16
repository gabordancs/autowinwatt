from __future__ import annotations

from winwatt_automation.runtime_mapping.safety import classify_safety, is_action_allowed, normalize_menu_text


def test_normalize_menu_text_removes_accents_and_spaces():
    assert normalize_menu_text("  Fájl megnyitása  ") == "fajl megnyitasa"


def test_classify_safety_levels():
    assert classify_safety(["Fájl", "Megnyitás"]) == "safe"
    assert classify_safety(["Fájl", "Export"]) == "caution"
    assert classify_safety(["Fájl", "Kilépés"]) == "blocked"


def test_is_action_allowed_by_mode():
    caution_path = ["Projekt", "Export"]
    blocked_path = ["Projekt", "Reset"]

    assert is_action_allowed(caution_path, mode="safe") is False
    assert is_action_allowed(caution_path, mode="caution") is True
    assert is_action_allowed(blocked_path, mode="caution") is False
    assert is_action_allowed(blocked_path, mode="blocked") is True
