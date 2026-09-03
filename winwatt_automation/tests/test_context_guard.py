import json

from winwatt_automation.runtime_mapping.context_guard import documented_dynamic_contexts, dynamic_context_signature, resolve_dynamic_context


def test_dynamic_context_signature_requires_all_three_context_sensitive_roots():
    assert dynamic_context_signature({"items": [{"caption": "Szerkesztés", "command_id": 10}]}) is None
    assert dynamic_context_signature({"items": [
        {"caption": "Szerkesztés", "command_id": 10},
        {"caption": "Csoport", "command_id": 20},
        {"caption": "Elem", "command_id": 30},
    ]}) == (10, 20, 30)


def test_documented_dynamic_contexts_discards_ambiguous_signatures(tmp_path):
    menu = {"items": [{"caption": "Szerkesztés", "command_id": 10}, {"caption": "Csoport", "command_id": 20}, {"caption": "Elem", "command_id": 30}]}
    (tmp_path / "02_first.json").write_text(json.dumps(menu), encoding="utf-8")
    (tmp_path / "03_second.json").write_text(json.dumps(menu), encoding="utf-8")
    assert documented_dynamic_contexts(tmp_path) == {}


def test_resolve_dynamic_context_uses_stable_mdi_title_not_restart_sensitive_ids(tmp_path):
    menu = {"items": [{"caption": "Szerkesztés", "command_id": 10}, {"caption": "Csoport", "command_id": 20}, {"caption": "Elem", "command_id": 30}]}
    (tmp_path / "02_Szerkezetek.json").write_text(json.dumps(menu), encoding="utf-8")
    result = resolve_dynamic_context(menu, active_title="Egycsöves körök", context_dir=tmp_path)
    assert result["recognized"] is False
    assert result["reason"] == "unknown_active_mdi_title"
    (tmp_path / "05_Egycsöves körök.json").write_text(json.dumps(menu), encoding="utf-8")
    assert resolve_dynamic_context({"items": [{"caption": "Szerkesztés", "command_id": 130}, {"caption": "Csoport", "command_id": 146}, {"caption": "Elem", "command_id": 150}]}, active_title="Egycsöves körök", context_dir=tmp_path)["recognized"] is True
