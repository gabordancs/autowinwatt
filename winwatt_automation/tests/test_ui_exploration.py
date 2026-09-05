from pathlib import Path

from winwatt_automation.research.ui_exploration import SandboxUIExplorer


class Info:
    def __init__(self, control_type: str, automation_id: str = "") -> None:
        self.control_type, self.automation_id = control_type, automation_id


class FakeControl:
    def __init__(self, caption: str, control_type: str = "Button", enabled: bool = True) -> None:
        self.caption, self.element_info, self.enabled = caption, Info(control_type, caption), enabled
        self.clicked = False
    def class_name(self): return "TButton"
    def window_text(self): return self.caption
    def is_visible(self): return True
    def is_enabled(self): return self.enabled
    def click_input(self): self.clicked = True
    def set_edit_text(self, value): self.caption = value


class FakeWindow(FakeControl):
    def __init__(self, controls):
        super().__init__("Sandbox", "Window")
        self.controls = controls
    def descendants(self): return self.controls


def test_only_discovered_safe_identity_can_activate(tmp_path: Path) -> None:
    sandbox = tmp_path / "sandbox" / "test.wwp"; sandbox.parent.mkdir(); sandbox.write_text("x")
    safe, destructive = FakeControl("Next"), FakeControl("Töröl")
    explorer = SandboxUIExplorer(FakeWindow([safe, destructive]), sandbox)
    state = explorer.inspect_window()
    safe_id = next(item.identity for item in state.controls if item.caption == "Next")
    delete_id = next(item.identity for item in state.controls if item.caption == "Töröl")
    assert explorer.activate_control("does-not-exist", 1).success is False
    assert explorer.activate_control(delete_id, 1).success is False
    result = explorer.activate_control(safe_id, 1)
    assert result.success and safe.clicked
    assert result.state_before and result.evidence_refs


def test_commit_caption_requires_separate_commit_budget(tmp_path: Path) -> None:
    sandbox = tmp_path / "sandbox" / "test.wwp"; sandbox.parent.mkdir(); sandbox.write_text("x")
    add = FakeControl("Felvesz...")
    explorer = SandboxUIExplorer(FakeWindow([add]), sandbox)
    identity = explorer.inspect_window().controls[0].identity
    result = explorer.activate_control(identity, 1)
    assert result.safety_class == "commit_candidate"
    assert result.success is False


def test_captionless_menu_item_is_a_safe_effect_probe_and_records_diff(tmp_path: Path) -> None:
    """An empty accessible name is evidence-poor, not an automatic blocker."""
    sandbox = tmp_path / "sandbox" / "test.wwp"; sandbox.parent.mkdir(); sandbox.write_text("x")
    anonymous = FakeControl("", "MenuItem")
    window = FakeWindow([anonymous])
    def open_effect():
        anonymous.clicked = True
        window.controls.append(FakeControl("Result", "Button"))
    anonymous.click_input = open_effect
    explorer = SandboxUIExplorer(window, sandbox)
    before = explorer.inspect_window()
    candidate = before.controls[0]
    assert candidate.caption == "" and candidate.control_type == "MenuItem" and candidate.enabled
    result = explorer.activate_control(candidate.identity, 1)
    assert result.success is True
    assert result.state_after is not None
    assert result.state_after.state_fingerprint != result.state_before.state_fingerprint
    assert result.controls_added
    assert result.evidence_refs[0].data["control_effect_only"] is True


def test_anonymous_probe_cannot_escape_sandbox(tmp_path: Path) -> None:
    outside = tmp_path / "not-a-sandbox.wwp"; outside.write_text("x")
    try:
        SandboxUIExplorer(FakeWindow([FakeControl("", "MenuItem")]), outside)
    except ValueError as exc:
        assert "sandbox" in str(exc)
    else:
        raise AssertionError("anonymous exploration must remain sandbox-only")


def test_observed_anonymous_edit_accepts_only_dummy_value_and_records_effect(tmp_path: Path) -> None:
    sandbox = tmp_path / "sandbox" / "test.wwp"; sandbox.parent.mkdir(); sandbox.write_text("x")
    edit, ok = FakeControl("", "Edit"), FakeControl("OK", "Button", enabled=False)
    window = FakeWindow([edit, ok])
    def set_value(value):
        edit.caption = value
        ok.enabled = True
    edit.set_edit_text = set_value
    explorer = SandboxUIExplorer(window, sandbox)
    edit_id = next(item.identity for item in explorer.inspect_window().controls if item.control_type == "Edit")
    assert explorer.set_control_value(edit_id, "not-a-dummy", 1).success is False
    result = explorer.set_control_value(edit_id, "AI_TEST_session_1", 2)
    assert result.success is True
    assert result.evidence_refs[0].data["value_after"] == "AI_TEST_session_1"
    assert result.state_after is not None
    assert result.state_after.state_fingerprint != result.state_before.state_fingerprint
