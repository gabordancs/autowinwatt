from pathlib import Path

from winwatt_automation.parser.program_map import build_program_map


def test_build_program_map_outputs_non_empty_catalogs(tmp_path: Path):
    result = build_program_map(xml_path=Path("data/raw/Hungarian.xml"), output_dir=tmp_path)

    counts = result["counts"]
    assert counts["forms"] > 0
    assert counts["controls"] > 0
    assert counts["actions"] > 0


def test_program_map_contains_expected_main_elements(tmp_path: Path):
    build_program_map(xml_path=Path("data/raw/Hungarian.xml"), output_dir=tmp_path)

    forms_catalog = (tmp_path / "forms_catalog.json").read_text(encoding="utf-8")
    actions_catalog = (tmp_path / "actions_catalog.json").read_text(encoding="utf-8")
    workflow_seeds = (tmp_path / "workflow_seeds.json").read_text(encoding="utf-8")

    assert "MainForm" in forms_catalog
    assert "OpenProjekt" in actions_catalog or "open_project" in actions_catalog
    assert "open_project" in workflow_seeds
    assert "save_project" in workflow_seeds


def test_menu_tree_and_dialog_catalog_have_entries(tmp_path: Path):
    build_program_map(xml_path=Path("data/raw/Hungarian.xml"), output_dir=tmp_path)

    menu_tree = (tmp_path / "menu_tree.json").read_text(encoding="utf-8")
    dialog_catalog = (tmp_path / "dialog_catalog.json").read_text(encoding="utf-8")

    assert "SaveProjekt" in menu_tree
    assert "AbsorptionTableForm" in dialog_catalog
