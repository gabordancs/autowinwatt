from __future__ import annotations

from pathlib import Path

import typer

from winwatt_automation.commands.registry import CommandRegistry
from winwatt_automation.config import PARSED_DATA_DIR, RAW_DATA_DIR
from winwatt_automation.parser.exporters import export_ui_model
from winwatt_automation.parser.semantic_classifier import classify_model
from winwatt_automation.parser.xml_parser import parse_hungarian_xml

app = typer.Typer(help="WinWatt automation CLI")


@app.command("parse-xml")
def parse_xml(
    xml_path: Path = typer.Option(RAW_DATA_DIR / "Hungarian.xml", exists=True, help="Path to Hungarian.xml"),
    output_path: Path = typer.Option(PARSED_DATA_DIR / "ui_model.json", help="Output JSON path"),
) -> None:
    model = classify_model(parse_hungarian_xml(xml_path))
    export_ui_model(model, output_path)
    typer.echo(f"Parsed and exported UI model to: {output_path}")


@app.command("export-ui-model")
def export_ui_model_cmd(
    xml_path: Path = typer.Option(RAW_DATA_DIR / "Hungarian.xml", exists=True, help="Path to Hungarian.xml"),
    output_path: Path = typer.Option(PARSED_DATA_DIR / "ui_model.json", help="Output JSON path"),
) -> None:
    model = classify_model(parse_hungarian_xml(xml_path))
    export_ui_model(model, output_path)
    typer.echo(f"Exported UI model to: {output_path}")


@app.command("list-forms")
def list_forms(
    xml_path: Path = typer.Option(RAW_DATA_DIR / "Hungarian.xml", exists=True, help="Path to Hungarian.xml"),
) -> None:
    model = classify_model(parse_hungarian_xml(xml_path))
    for form in model.forms:
        typer.echo(f"{form.name} ({form.form_type})")


@app.command("list-actions")
def list_actions(
    xml_path: Path = typer.Option(RAW_DATA_DIR / "Hungarian.xml", exists=True, help="Path to Hungarian.xml"),
) -> None:
    model = classify_model(parse_hungarian_xml(xml_path))
    registry = CommandRegistry()
    registry.build_from_ui_model(model)
    for command in registry.commands:
        typer.echo(f"{command.command_name} [{command.source_form}.{command.source_item_name}]")


if __name__ == "__main__":
    app()
