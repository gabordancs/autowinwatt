from __future__ import annotations

from pathlib import Path
import json
import os

import typer

from winwatt_automation.commands.registry import CommandRegistry
from winwatt_automation.config import PARSED_DATA_DIR, RAW_DATA_DIR
from winwatt_automation.parser.exporters import export_ui_model
from winwatt_automation.parser.program_map import build_program_map
from winwatt_automation.parser.semantic_classifier import classify_model
from winwatt_automation.parser.xml_parser import parse_hungarian_xml
from winwatt_automation.domain.project import PrepareRoomsInput
from winwatt_automation.services.room_service import RoomService
from winwatt_automation.experiments.runner import ExperimentRunner
from winwatt_automation.knowledge.models import ExperimentSpec
from winwatt_automation.knowledge.store import KnowledgeStore

app = typer.Typer(help="WinWatt automation CLI")
knowledge_app = typer.Typer(help="Inspect deterministic semantic knowledge")
experiment_app = typer.Typer(help="Run sandbox-only deterministic experiments")
app.add_typer(knowledge_app, name="knowledge")
app.add_typer(experiment_app, name="experiment")


def _json_output(value: object) -> None:
    typer.echo(json.dumps(value, ensure_ascii=False, default=str))


@knowledge_app.command("show")
def knowledge_show(concept: str = typer.Argument(..., help="Semantic concept/capability id")) -> None:
    """Return one concept and its associated capability as JSON."""
    store = KnowledgeStore()
    item = store.get_concept(concept)
    if item is None:
        _json_output({"error": "concept_not_found", "concept": concept})
        raise typer.Exit(code=1)
    capability = store.get_capability(concept)
    _json_output({"concept": item.model_dump(mode="json"), "capability": capability.model_dump(mode="json") if capability else None})


@knowledge_app.command("search")
def knowledge_search(query: str = typer.Argument(..., help="Concept text to search")) -> None:
    """Search semantic concepts; output is intentionally JSON-only."""
    store = KnowledgeStore()
    _json_output({"query": query, "concepts": [item.model_dump(mode="json") for item in store.search_concepts(query)]})


@experiment_app.command("run")
def experiment_run(
    experiment_path: Path = typer.Argument(..., exists=True, readable=True, help="ExperimentSpec JSON file"),
    output_dir: Path = typer.Option(Path("data/runtime_maps/experiments"), help="Parent directory for copied sandbox projects"),
) -> None:
    """Run an approved semantic action only when WinWatt E2E is explicitly enabled."""
    if os.environ.get("WINWATT_E2E") != "1":
        _json_output({"error": "e2e_disabled", "hint": "Set WINWATT_E2E=1 to permit a sandbox WinWatt experiment."})
        raise typer.Exit(code=2)
    spec = ExperimentSpec.model_validate_json(experiment_path.read_text(encoding="utf-8"))
    source = Path(spec.source_project) if spec.source_project else None
    if source is not None and not source.is_absolute():
        source = (experiment_path.parent / source).resolve()
    store = KnowledgeStore()
    result = ExperimentRunner(output_dir=output_dir.resolve()).run(spec, source_project=source)
    store.store_experiment_result(result)
    promoted = None
    if result.success:
        promoted = store.promote_to_verified(spec.target_capability, result)
    _json_output({"result": result.model_dump(mode="json"), "concept": promoted.model_dump(mode="json") if promoted else store.get_concept(spec.target_capability).model_dump(mode="json")})
    if not result.success:
        raise typer.Exit(code=1)


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


@app.command("build-program-map")
def build_program_map_cmd(
    xml_path: Path = typer.Option(RAW_DATA_DIR / "Hungarian.xml", exists=True, help="Path to Hungarian.xml"),
    output_dir: Path = typer.Option(PARSED_DATA_DIR, help="Output directory for generated catalogs"),
) -> None:
    result = build_program_map(xml_path=xml_path, output_dir=output_dir)
    counts = result["counts"]
    typer.echo(f"Program map generated under: {output_dir}")
    typer.echo(f"forms: {counts['forms']}")
    typer.echo(f"controls: {counts['controls']}")
    typer.echo(f"actions: {counts['actions']}")
    typer.echo(f"dialogs: {counts['dialogs']}")
    typer.echo(f"workflow_seeds: {counts['workflow_seeds']}")


@app.command("prepare-rooms")
def prepare_rooms(
    input_path: Path = typer.Argument(..., exists=True, readable=True, help="JSON PrepareRoomsInput file"),
    output_dir: Path = typer.Option(Path("data/runtime_maps/mvp_runs"), help="Parent directory for the disposable sandbox"),
) -> None:
    """Create, save and reopen rooms in a newly copied sandbox project."""
    import json
    from datetime import datetime, timezone

    payload = PrepareRoomsInput.model_validate_json(input_path.read_text(encoding="utf-8"))
    source = payload.project_path
    if not source.is_absolute():
        source = (input_path.parent / source).resolve()
    run_dir = output_dir.resolve() / datetime.now(timezone.utc).strftime("prepare_rooms_%Y%m%dT%H%M%SZ")
    service = RoomService()
    sandbox = service.create_sandbox(source, run_dir / "sandbox" / "testwwp.wwp")
    result = service.prepare_rooms(payload.rooms, sandbox)
    report = run_dir / "operation_result.json"
    report.parent.mkdir(parents=True, exist_ok=True)
    report.write_text(result.model_dump_json(indent=2) + "\n", encoding="utf-8")
    typer.echo(json.dumps({"sandbox_project": str(sandbox), "report": str(report), **result.model_dump()}, ensure_ascii=False, default=str))
    if not result.success:
        raise typer.Exit(code=1)


if __name__ == "__main__":
    app()
