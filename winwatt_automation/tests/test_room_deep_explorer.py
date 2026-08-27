from collections import deque

from winwatt_automation.runtime_mapping.room_deep_explorer import ControlAction, _prune_queue, action_identity, state_diff, state_hash


def test_state_hash_is_deterministic_for_equal_structures() -> None:
    first = {"title": "x", "class_name": "y", "controls": [{"name": "a"}]}
    second = {"controls": [{"name": "a"}], "class_name": "y", "title": "x"}
    assert state_hash(first) == state_hash(second)


def test_state_hash_ignores_recreated_automation_handles() -> None:
    first = {"title": "x", "class_name": "y", "controls": [{"name": "a", "automation_id": "101"}]}
    second = {"title": "x", "class_name": "y", "controls": [{"name": "a", "automation_id": "202"}]}
    assert state_hash(first) == state_hash(second)


def test_state_hash_keeps_selected_value_distinct() -> None:
    first = {"title": "x", "class_name": "y", "controls": [{"name": "a", "value": "inside"}]}
    second = {"title": "x", "class_name": "y", "controls": [{"name": "a", "value": "outside"}]}
    assert state_hash(first) != state_hash(second)


def test_control_action_is_serializable_for_replay() -> None:
    action = ControlAction("Button", "Szerkezetek...", "id", (1, 2, 3, 4))
    assert action.operation == "activate"


def test_action_identity_ignores_recreated_automation_id() -> None:
    first = ControlAction("Button", "Módosít...", "101", (1, 2, 3, 4))
    second = ControlAction("Button", "Módosít...", "202", (1, 2, 3, 4))
    assert action_identity(first) == action_identity(second)


def test_state_diff_records_added_and_removed_controls() -> None:
    old = {"title": "x", "class_name": "Form", "controls": [{"control_type": "Button", "class_name": "TButton", "name": "A", "rect": (0, 0, 1, 1), "enabled": True, "visible": True}]}
    new = {"title": "x", "class_name": "Form", "controls": [{"control_type": "Button", "class_name": "TButton", "name": "B", "rect": (0, 0, 1, 1), "enabled": True, "visible": True}]}
    diff = state_diff(old, new)
    assert diff["changed"] is True
    assert diff["added_controls"][0]["name"] == "B"
    assert diff["removed_controls"][0]["name"] == "A"


def test_state_diff_records_value_change() -> None:
    old = {"title": "x", "class_name": "Form", "controls": [{"control_type": "ComboBox", "class_name": "TComboBox", "name": "", "rect": (0, 0, 1, 1), "enabled": True, "visible": True, "value": "A"}]}
    new = {"title": "x", "class_name": "Form", "controls": [{"control_type": "ComboBox", "class_name": "TComboBox", "name": "", "rect": (0, 0, 1, 1), "enabled": True, "visible": True, "value": "B"}]}
    diff = state_diff(old, new)
    assert diff["changed"] is True
    assert diff["value_changes"][0]["current_value"] == "B"


def test_prune_queue_removes_exhausted_path_but_keeps_other_work() -> None:
    failed = ControlAction("Button", "Hibás", "1", (1, 1, 2, 2))
    useful = ControlAction("Button", "Jó", "2", (3, 3, 4, 4))
    queue, removed = _prune_queue(
        deque([([failed], None), ([useful], None), ([useful], None)]), [], [],
        [{"path": [failed.__dict__], "error": "x", "attempt": attempt} for attempt in range(1, 4)],
    )
    assert removed == 1
    assert list(queue) == [([useful], None)]
