import json

from winwatt_automation.dev.identity_loop_check import _atomic_json


def test_iteration_one_audit_survives_following_timeout(tmp_path):
    target = tmp_path / "identity_loop_live_audit.json"
    _atomic_json(target, {"session_id": "identity", "status": "running", "iterations": [{"iteration": 1, "executed_action": {"kind": "inspect_ui"}}]})
    _atomic_json(target, {"session_id": "identity", "status": "stopped", "stop_reason": "planner/provider call timed out after 1.0s", "iterations": [{"iteration": 1, "executed_action": {"kind": "inspect_ui"}}, {"iteration": 2, "error": "planner/provider call timed out after 1.0s"}]})
    saved = json.loads(target.read_text(encoding="utf-8"))
    assert saved["iterations"][0]["executed_action"]["kind"] == "inspect_ui"
    assert saved["iterations"][1]["error"].startswith("planner/provider")
