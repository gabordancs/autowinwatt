"""Record visible-but-not-automated native menu branches conservatively."""

from __future__ import annotations

import json
from pathlib import Path

from winwatt_automation.live_ui.native_menu import enumerate_native_menu


PROJECT_ROOT = Path(__file__).resolve().parents[3]

RUNTIME_PROBES = {
    55: {
        "result": "opened_and_cancelled",
        "dialog_class": "TChangeBoundarisForm",
        "dialog_title": "Szerkezetek cseréje",
        "forbidden_effects": ["change_structures", "create_or_delete_boundaries", "confirm_dialog"],
    },
    56: {
        "result": "opened_and_cancelled",
        "dialog_class": "TChangeCeilingForm",
        "dialog_title": "Födémek törlése, létrehozása",
        "forbidden_effects": ["create_ceiling", "delete_ceiling", "confirm_dialog"],
    },
    57: {
        "result": "opened_and_cancelled",
        "dialog_class": "TChangeTempForm",
        "dialog_title": "Hőmérsékletek cseréje",
        "forbidden_effects": ["change_temperature", "confirm_dialog"],
    },
    58: {
        "result": "opened_and_cancelled",
        "dialog_class": "TChangeFiltrationForm",
        "dialog_title": "Téli filtráció számítás cseréje",
        "forbidden_effects": ["change_filtration_calculation", "confirm_dialog"],
    },
    59: {
        "result": "opened_and_cancelled",
        "dialog_class": "TChangeRoomByMakroForm",
        "dialog_title": "Helyiségek kitöltése makróval",
        "forbidden_effects": ["run_macro", "fill_rooms", "confirm_dialog"],
    },
    60: {
        "result": "opened_and_cancelled",
        "dialog_class": "TRotateRoomsForm",
        "dialog_title": "Helyis\u00e9gek forgat\u00e1sa, t\u00fckr\u00f6z\u00e9se",
        "forbidden_effects": ["rotate_rooms", "mirror_rooms", "confirm_dialog"],
    },
    61: {
        "result": "opened_and_cancelled",
        "dialog_class": "TChangeBuildingReferenceForm",
        "dialog_title": "Helyis\u00e9gek \u00e1tsorol\u00e1sa m\u00e1s \u00e9p\u00fcletbe, l\u00e9gtechnikai rendszerbe",
        "forbidden_effects": ["reassign_rooms", "change_building_reference", "change_ventilation_system", "confirm_dialog"],
    },
    62: {
        "result": "opened_and_cancelled",
        "dialog_class": "TChangeRadiatorForm",
        "dialog_title": "K\u00e9tcs\u00f6ves radi\u00e1torok m\u00f3dos\u00edt\u00e1sa",
        "forbidden_effects": ["change_two_pipe_radiators", "confirm_dialog"],
    },
    71: {
        "result": "opened_and_cancelled",
        "dialog_class": "TChangeHydraulicsForm",
        "dialog_title": "T\u00edpusm\u00f3dos\u00edt\u00e1sok, m\u00e9retek",
        "forbidden_effects": ["change_hydraulic_types", "change_dimensions", "confirm_dialog"],
    },
    72: {
        "result": "opened_and_cancelled",
        "dialog_class": "TGeneraleChangeForm",
        "dialog_title": "\u00c1ltal\u00e1nos adatcsere",
        "forbidden_effects": ["bulk_change_project_data", "confirm_dialog"],
    },
    73: {
        "result": "disabled_in_current_project",
        "dialog_class": None,
        "dialog_title": None,
        "forbidden_effects": ["unknown_until_enabled_runtime_evidence"],
    },
    74: {
        "result": "opened_and_cancelled",
        "dialog_class": "Dialog",
        "dialog_title": "Megnyit\u00e1s",
        "forbidden_effects": ["select_external_file", "import_unknown_format", "confirm_dialog"],
    },
    75: {
        "result": "opened_and_cancelled",
        "dialog_class": "Dialog",
        "dialog_title": "Megnyit\u00e1s",
        "forbidden_effects": ["select_external_file", "import_unknown_format", "confirm_dialog"],
    },
    76: {
        "result": "opened_and_cancelled",
        "dialog_class": "Dialog",
        "dialog_title": "Ment\u00e9s m\u00e1sk\u00e9nt",
        "forbidden_effects": ["select_external_destination", "export_unknown_format", "confirm_dialog"],
    },
    77: {
        "result": "opened_and_cancelled",
        "dialog_class": "Dialog",
        "dialog_title": "Megnyit\u00e1s",
        "forbidden_effects": ["select_external_file", "import_unknown_format", "confirm_dialog"],
    },
    79: {
        "result": "opened_and_cancelled",
        "dialog_class": "Dialog",
        "dialog_title": "Megnyit\u00e1s",
        "forbidden_effects": ["select_external_file", "import_unknown_format", "confirm_dialog"],
    },
}


def _dialog_mappings() -> dict[int, dict[str, object]]:
    """Index value-redacted inner-dialog maps captured by map_high_risk_dialog."""
    mapping_dir = PROJECT_ROOT / "data" / "runtime_maps" / "high_risk_dialogs_9_60"
    mappings: dict[int, dict[str, object]] = {}
    for path in mapping_dir.glob("*.json"):
        payload = json.loads(path.read_text(encoding="utf-8"))
        command_id = payload.get("command_id")
        if not isinstance(command_id, int):
            continue
        mappings[command_id] = {
            "path": str(path.relative_to(PROJECT_ROOT)).replace("\\", "/"),
            "result": payload.get("result"),
            "control_count": payload.get("control_count"),
            "screenshot": payload.get("screenshot"),
        }
    return mappings


def main() -> int:
    menu = enumerate_native_menu()
    tools_root = next(item for item in menu["items"] if item["caption"] == "Eszközök")
    dialog_mappings = _dialog_mappings()
    registry = {
        "schema_version": 1,
        "root": {"caption": tools_root["caption"], "command_id": tools_root["command_id"]},
        "policy": "not_exposed_until_each_child_has_separate_runtime_evidence_and_explicit_effect_policy",
        "reason": "The visible Tools menu contains project transformations, external project interchange, and optimization operations; owner-drawn child captions are not reliable in native enumeration.",
        "visual_evidence": "data/snapshots/deep_project_top_menus_9_60/02_Eszközök.png",
        "children": [
            {
                "index": child["index"],
                "command_id": child["command_id"],
                "enabled": child["enabled"],
                "caption_reliable": child["caption_reliable"],
                "admission": "not_exposed",
                "runtime_probe": RUNTIME_PROBES.get(child["command_id"]),
                "dialog_mapping": dialog_mappings.get(child["command_id"]),
            }
            for child in tools_root["children"]
        ],
    }
    output = PROJECT_ROOT / "data" / "runtime_maps" / "high_risk_tools_menu_9_60.json"
    output.write_text(json.dumps(registry, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"output": str(output), "child_count": len(registry["children"])}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
