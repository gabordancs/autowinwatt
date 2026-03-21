from __future__ import annotations

from winwatt_automation.scripts import map_full_program


def test_parse_top_menus_none_uses_runtime_discovery_default():
    assert map_full_program._parse_top_menus(None) is None


def test_close_winwatt_after_mapping_prefers_window_close(monkeypatch):
    closed = {"value": False}

    class _Window:
        def close(self):
            closed["value"] = True

    monkeypatch.setattr(map_full_program, "get_cached_main_window", lambda: _Window())
    monkeypatch.setattr(map_full_program, "_wait_for_window_to_close", lambda main_window, timeout_s=5.0, poll_interval_s=0.2: True)

    result = map_full_program._close_winwatt_after_mapping()

    assert closed["value"] is True
    assert result["closed"] is True
    assert result["method"] == "window.close"

from winwatt_automation.runtime_mapping.program_mapper import DEFAULT_TOP_MENUS


def test_default_top_menu_targets_include_all_discovered_menus_from_logs():
    assert DEFAULT_TOP_MENUS == ["Fájl", "Jegyzékek", "Adatbázis...", "Beállítások", "Ablak", "Súgó"]


def test_parser_placeholder_modal_policy_default():
    parser = map_full_program.build_parser()
    args = parser.parse_args([])
    assert args.placeholder_modal_policy == "submenu_only"


def test_parser_recent_projects_policy_default():
    parser = map_full_program.build_parser()
    args = parser.parse_args([])
    assert args.recent_projects_policy == "skip_recent_projects"


def test_parse_top_menus_accepts_semicolon_separated_targets():
    assert map_full_program._parse_top_menus("Fájl;Jegyzékek") == ["fájl", "jegyzékek"]


def test_parser_single_row_probe_defaults():
    parser = map_full_program.build_parser()
    args = parser.parse_args([])
    assert args.probe_top_menu is None
    assert args.probe_row_text is None
    assert args.probe_row_index is None
    assert args.probe_repeat == 1
