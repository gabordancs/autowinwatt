from winwatt_automation.runtime_mapping.command_catalog import build_runtime_command_catalog


def test_runtime_command_catalog_exposes_only_constrained_verified_workflows():
    catalog = build_runtime_command_catalog()
    commands = {command["stable_key"]: command for command in catalog["commands"]}

    assert set(commands) == {
        "MainForm.NewProjekt",
        "MainForm.OpenProjekt",
        "MainForm.HelpAbout",
        "MainForm.ProgramOptions",
        "MainForm.ProjektOptions",
        "MainForm.HelpContent",
        "MainForm.ProjektData",
        "MainForm.XMLExportAction",
        "MainForm.XMLImportAction",
        "MainForm.CreateReportAction",
    }
    assert commands["MainForm.OpenProjekt"]["safety_level"] == "probe_only"
    assert "confirm_file_name" in commands["MainForm.OpenProjekt"]["forbidden_effects"]
    assert commands["MainForm.NewProjekt"]["runtime_evidence"] == "new_project_dialog_detected_and_cancelled"
    assert catalog["unexposed_observations"][0]["stable_key"] == "MainForm.DatabaseAction"
    assert catalog["unexposed_observations"][0]["admission"] == "not_exposed"
    assert commands["MainForm.ProgramOptions"]["native_menu"] == {"parent_command_id": 88, "command_id": 89}
    assert commands["MainForm.ProjektOptions"]["native_menu"] == {"parent_command_id": 88, "command_id": 90}
    assert commands["MainForm.HelpContent"]["native_menu"] == {"parent_command_id": 97, "command_id": 98}
    assert commands["MainForm.ProjektData"]["native_menu"] == {"parent_command_id": 1, "command_id": 7}
    assert commands["MainForm.XMLExportAction"]["native_menu"] == {"parent_command_id": 1, "command_id": 9}
    assert commands["MainForm.XMLImportAction"]["native_menu"] == {"parent_command_id": 1, "command_id": 10}
    assert "confirm_import" in commands["MainForm.XMLImportAction"]["forbidden_effects"]
    assert commands["MainForm.CreateReportAction"]["native_menu"] == {"parent_command_id": 1, "command_id": 19}
