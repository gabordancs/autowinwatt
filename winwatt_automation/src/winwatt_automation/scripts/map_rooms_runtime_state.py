"""Capture the Helyiségek MDI runtime state and map its New Element route."""

from __future__ import annotations

import json

from winwatt_automation.runtime_mapping.mdi_state_model import (
    activate_rooms_catalog,
    capture_active_mdi_state,
    map_rooms_new_element_menu,
)


def main() -> int:
    activation = activate_rooms_catalog()
    state = capture_active_mdi_state()
    route = map_rooms_new_element_menu()
    print(json.dumps({
        "activation": activation,
        "state_id": state["state_id"],
        "menu_structure_changed": state["menu_diff_from_previous"]["changed"],
        "new_element_row_found": route["row_found"],
        "new_element_row_index": route["route"][1]["row_index"],
    }, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
