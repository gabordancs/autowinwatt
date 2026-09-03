from winwatt_automation.commands import safe_runtime_commands


def test_resolve_safe_command_accepts_only_exact_approved_intents():
    assert safe_runtime_commands.resolve_safe_command("  NÉVJEGY  ")[0] == "MainForm.HelpAbout"
    assert safe_runtime_commands.resolve_safe_command("projekt törlése") is None
    assert safe_runtime_commands.resolve_safe_command("nyisd meg a projektemet") is None


def test_resolve_safe_command_exposes_only_newly_verified_probe_intents():
    assert safe_runtime_commands.resolve_safe_command("xml import ellenorzese")[0] == "MainForm.XMLImportAction"
    assert safe_runtime_commands.resolve_safe_command("egyedi riport sablon ellenorzese")[0] == "MainForm.CreateReportAction"


def test_execute_safe_command_rejects_unknown_without_starting_workflow(monkeypatch):
    monkeypatch.setattr(safe_runtime_commands, "start_run", lambda *_args, **_kwargs: (_ for _ in ()).throw(AssertionError("must not log/run")))

    result = safe_runtime_commands.execute_safe_command("projekt törlése")

    assert result["accepted"] is False
    assert result["reason"] == "unknown_or_unsafe_command"


def test_execute_safe_command_logs_and_returns_workflow_postconditions(monkeypatch):
    events = []
    finalized = []
    run_ctx = type("Run", (), {"run_id": "safe-1"})()
    monkeypatch.setattr(safe_runtime_commands, "start_run", lambda *_args, **_kwargs: run_ctx)
    monkeypatch.setattr(safe_runtime_commands, "update_status", lambda *_args, **_kwargs: None)
    monkeypatch.setattr(safe_runtime_commands, "record_event", lambda _ctx, event, payload: events.append((event, payload)))
    monkeypatch.setattr(safe_runtime_commands, "finalize_run", lambda _ctx, **kwargs: finalized.append(kwargs))
    monkeypatch.setitem(safe_runtime_commands._COMMANDS, "névjegy", ("MainForm.HelpAbout", lambda: {"success": True, "dialog_dismissed": True}))

    result = safe_runtime_commands.execute_safe_command("névjegy")

    assert result["success"] is True
    assert result["run_id"] == "safe-1"
    assert [event for event, _ in events] == ["command_accepted", "workflow_result"]
    assert finalized[0]["exit_code"] == 0
