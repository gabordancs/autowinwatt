from winwatt_automation.runtime_mapping.authorized_explorer import PROJECT_ROOT, _project_relative, menu_leaf_frontier


def test_menu_leaf_frontier_keeps_all_leaves_and_never_executes_them() -> None:
    menu = {
        "items": [{
            "caption": "Elem", "caption_reliable": True, "command_id": 10, "enabled": True,
            "children": [
                {"caption": "L\u00e9trehoz", "caption_reliable": True, "command_id": 11, "enabled": True, "children": []},
                {"caption": "T\u00f6r\u00f6l", "caption_reliable": True, "command_id": 12, "enabled": True, "children": []},
            ],
        }],
    }
    leaves = menu_leaf_frontier(menu)
    assert [leaf["command_id"] for leaf in leaves] == [11, 12]
    assert all(leaf["execution"] == "catalog_only_unknown_leaf" for leaf in leaves)
    assert leaves[1]["safety"] == "blocked"


def test_project_relative_accepts_relative_artifact_path() -> None:
    assert _project_relative(PROJECT_ROOT / "data" / "artifact.json") == "data/artifact.json"
