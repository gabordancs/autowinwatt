from __future__ import annotations

from winwatt_automation.runtime_mapping.menu_text import menu_titles_equal, normalize_menu_title


def test_menu_titles_equal_ellipsis_ascii():
    assert menu_titles_equal("Adatbázisok...", "Adatbázisok")


def test_menu_titles_equal_ellipsis_unicode():
    assert menu_titles_equal("Adatbázisok…", "Adatbázisok")


def test_menu_titles_equal_accelerator_and_ellipsis():
    assert menu_titles_equal("&Adatbázisok...", "Adatbázisok")


def test_normalize_menu_title_trims_and_lowercases():
    assert normalize_menu_title("  Adatbázisok… ") == "adatbázisok"


def test_normalize_menu_title_variants_share_same_value():
    variants = [
        "Adatbázisok...",
        "Adatbázisok…",
        "Adatbázisok",
        "&Adatbázisok...",
        "  Adatbázisok… ",
    ]
    normalized = {normalize_menu_title(item) for item in variants}
    assert normalized == {"adatbázisok"}
