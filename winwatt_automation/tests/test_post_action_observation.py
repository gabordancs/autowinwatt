from types import SimpleNamespace

from winwatt_automation.research.orchestrator import catalog_new_ui_state


def _snapshot(fingerprint: str, window: str, *captions: str):
    return SimpleNamespace(
        state_fingerprint=fingerprint,
        class_name=window,
        title=window,
        controls=[SimpleNamespace(identity=f"id-{caption}", caption=caption, control_type="Button", enabled=True) for caption in captions],
    )


def test_new_catalog_navigation_is_auto_inspected_before_replan() -> None:
    registry = {}
    triggered, trace = catalog_new_ui_state(
        registry, _snapshot("structure-fp", "StructureCatalog", "Új elem", "Módosít"),
        iteration=2, source_action="open_known_navigation", semantic_context="catalog creation",
    )
    assert triggered is True
    assert trace.action == "auto_inspect"
    assert [item.caption for item in trace.discovered_controls] == ["Új elem", "Módosít"]
    assert registry["structure-fp"].source_action == "open_known_navigation"
    repeated, _ = catalog_new_ui_state(registry, _snapshot("structure-fp", "StructureCatalog", "Új elem"), iteration=3, source_action="open_known_navigation", semantic_context="catalog creation")
    assert repeated is False


def test_hvac_navigation_uses_same_general_post_action_policy() -> None:
    registry = {}
    triggered, trace = catalog_new_ui_state(
        registry, _snapshot("hvac-fp", "HVAC", "Körök", "Új elem"),
        iteration=7, source_action="activate_control", semantic_context="hvac screen",
    )
    assert triggered is True
    assert trace.resulting_window == "HVAC"
    assert {item.caption for item in trace.discovered_controls} == {"Körök", "Új elem"}
