from __future__ import annotations

from winwatt_automation.runtime_mapping.models import RuntimeStateMap
from winwatt_automation.runtime_mapping.program_mapper import compare_runtime_states


def _state_map(state_id: str, top_menus: list[str], action_paths: list[list[str]]) -> RuntimeStateMap:
    return RuntimeStateMap(
        state_id=state_id,
        snapshot={"state_id": state_id},
        top_menus=[{"text": item} for item in top_menus],
        menu_rows=[],
        actions=[{"menu_path": path} for path in action_paths],
        dialogs=[],
        windows=[],
        skipped_actions=[],
    )


def test_compare_runtime_states_detects_menu_and_action_differences():
    state_a = _state_map("a", ["Fájl", "Nézet"], [["Fájl", "Megnyitás"], ["Nézet", "Nagyítás"]])
    state_b = _state_map("b", ["Fájl", "Projekt"], [["Fájl", "Megnyitás"], ["Projekt", "Export"]])

    diff = compare_runtime_states(state_a, state_b)

    assert diff.top_menu_diff["only_in_a"] == ["Nézet"]
    assert diff.top_menu_diff["only_in_b"] == ["Projekt"]
    assert ["Nézet", "Nagyítás"] in diff.menu_action_diff["only_in_a"]
    assert ["Projekt", "Export"] in diff.menu_action_diff["only_in_b"]
    assert diff.summary["shared_top_menus"] == 1
    assert diff.summary["actions_only_in_a"] == 1
    assert diff.summary["actions_only_in_b"] == 1
