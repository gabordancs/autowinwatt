from __future__ import annotations

from pathlib import Path
import json
import os
from uuid import uuid4

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
from winwatt_automation.knowledge.models import AssignExistingBoundaryStructureInput, ExperimentSpec, Hypothesis, KnowledgeStatus
from winwatt_automation.knowledge.store import KnowledgeStore
from winwatt_automation.research.manual_index import ManualIndex
from winwatt_automation.research.models import ResearchEvidence
from winwatt_automation.planner.planner import ResearchPlanValidationError, ResearchPlanner
from winwatt_automation.planner.provider import OpenAIProvider
from winwatt_automation.discovery.models import DiscoveryGoal, StructureClassificationGoal
from winwatt_automation.discovery.runner import LiveRoomBoundaryDiscoveryUI, ResearchDiscoveryRunner
from winwatt_automation.research.orchestrator import ResearchBudget, ResearchOrchestrator

app = typer.Typer(help="WinWatt automation CLI")
knowledge_app = typer.Typer(help="Inspect deterministic semantic knowledge")
experiment_app = typer.Typer(help="Run sandbox-only deterministic experiments")
sources_app = typer.Typer(help="Inspect locally indexed research sources")
manual_app = typer.Typer(help="Index and search the WinWatt manual")
research_app = typer.Typer(help="Dry-run LLM-guided research planning")
discover_app = typer.Typer(help="Bounded sandbox-only UI capability discovery")
app.add_typer(knowledge_app, name="knowledge")
app.add_typer(experiment_app, name="experiment")
app.add_typer(sources_app, name="sources")
app.add_typer(manual_app, name="manual")
app.add_typer(research_app, name="research")
app.add_typer(discover_app, name="discover")

_PACKAGE_ROOT = Path(__file__).resolve().parents[3]
_REPO_ROOT = Path(__file__).resolve().parents[4]
DEFAULT_MANUAL_PATH = _REPO_ROOT / "WinWatt.pdf"
DEFAULT_MANUAL_INDEX = _PACKAGE_ROOT / "data" / "research" / "winwatt_manual_index.json"


def _json_output(value: object) -> None:
    # Windows consoles are often CP1250; escaped JSON remains portable and machine-readable.
    typer.echo(json.dumps(value, ensure_ascii=True, default=str))


@knowledge_app.command("show")
def knowledge_show(concept: str = typer.Argument(..., help="Semantic concept/capability id")) -> None:
    """Return one concept and its associated capability as JSON."""
    store = KnowledgeStore()
    item = store.get_concept(concept)
    if item is None:
        _json_output({"concept": {"concept": concept, "status": KnowledgeStatus.UNKNOWN}, "capability": None})
        return
    capability = store.get_capability(concept)
    _json_output({"concept": item.model_dump(mode="json"), "capability": capability.model_dump(mode="json") if capability else None})


@knowledge_app.command("search")
def knowledge_search(query: str = typer.Argument(..., help="Concept text to search")) -> None:
    """Search semantic concepts; output is intentionally JSON-only."""
    store = KnowledgeStore()
    _json_output({"query": query, "concepts": [item.model_dump(mode="json") for item in store.search_concepts(query)]})


@knowledge_app.command("evidence")
def knowledge_evidence(concept: str = typer.Argument(..., help="Concept/capability id")) -> None:
    """Return deterministic and manual provenance separately as JSON."""
    store = KnowledgeStore()
    item = store.get_concept(concept)
    _json_output({
        "concept": concept,
        "concept_exists": item is not None,
        "knowledge_evidence": [] if item is None else [e.model_dump(mode="json") for e in item.evidence],
        "manual_evidence": [e.model_dump(mode="json") for e in store.get_concept_research_evidence(concept)],
    })


@knowledge_app.command("hypothesize")
def knowledge_hypothesize(
    concept: str = typer.Argument(..., help="Target semantic concept/capability"),
    hypothesis_id: str = typer.Argument(..., help="Stable hypothesis id"),
    semantic_guess: str = typer.Argument(..., help="Human/heuristic semantic interpretation"),
    confidence: float = typer.Option(0.5, min=0.0, max=1.0),
) -> None:
    """Create a non-verified hypothesis; it cannot execute UI actions by itself."""
    store = KnowledgeStore()
    hypothesis = store.store_hypothesis(Hypothesis(
        hypothesis_id=hypothesis_id, target_capability=concept,
        semantic_guess=semantic_guess, confidence=confidence,
    ))
    _json_output({"hypothesis": hypothesis.model_dump(mode="json"), "concept": store.get_concept(concept).model_dump(mode="json")})


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
    if store.get_hypothesis(spec.hypothesis_id) is None:
        store.store_hypothesis(Hypothesis(
            hypothesis_id=spec.hypothesis_id,
            target_capability=spec.target_capability,
            semantic_guess=f"Experiment-provided meaning for {spec.target_capability}",
            confidence=0.5,
        ))
    result = ExperimentRunner(output_dir=output_dir.resolve()).run(spec, source_project=source)
    store.store_experiment_result(result)
    promoted = None
    if result.success:
        promoted = store.promote_to_verified(spec.target_capability, result)
    _json_output({"result": result.model_dump(mode="json"), "concept": promoted.model_dump(mode="json") if promoted else store.get_concept(spec.target_capability).model_dump(mode="json")})
    if not result.success:
        raise typer.Exit(code=1)


@experiment_app.command("assign-boundary-structure")
def experiment_assign_boundary_structure(
    reference: str = typer.Option(..., "--reference", help="Exact discovered catalogue caption"),
    room: str = typer.Option("Discovery room", "--room"),
    source_project: Path = typer.Option(Path("tests/testwwp.wwp"), "--project", exists=True, readable=True),
    expected_kind: str | None = typer.Option(None, "--expected-kind"),
    hypothesis_id: str | None = typer.Option(None, "--hypothesis-id"),
    output_dir: Path = typer.Option(Path("data/runtime_maps/experiments")),
) -> None:
    """Assign one discovered boundary reference in a sandbox and verify it after reopen."""
    if os.environ.get("WINWATT_E2E") != "1":
        _json_output({"error": "e2e_disabled", "hint": "Set WINWATT_E2E=1 to permit a sandbox assignment experiment."})
        raise typer.Exit(code=2)
    stable_hypothesis = hypothesis_id or f"hyp_assign_existing_{uuid4().hex}"
    request = AssignExistingBoundaryStructureInput(
        hypothesis_id=stable_hypothesis, room_identifier=room, structure_reference=reference,
        expected_kind=expected_kind, sandbox_project=str(source_project.resolve()),
    )
    spec = request.as_experiment_spec()
    store = KnowledgeStore()
    if store.get_hypothesis(spec.hypothesis_id) is None:
        store.store_hypothesis(Hypothesis(
            hypothesis_id=spec.hypothesis_id, target_capability=spec.target_capability,
            semantic_guess="A discovered structure reference can be assigned to a room and persist after Save As/reopen.",
            confidence=0.5,
        ))
    result = ExperimentRunner(output_dir=output_dir.resolve()).run(spec, source_project=source_project.resolve())
    store.store_experiment_result(result)
    promoted = store.promote_to_verified(spec.target_capability, result) if result.success else None
    _json_output({"input": request.model_dump(mode="json"), "result": result.model_dump(mode="json"), "concept": (promoted or store.get_concept(spec.target_capability)).model_dump(mode="json")})
    if not result.success:
        raise typer.Exit(code=1)


def _load_manual_index(pdf_path: Path, index_path: Path) -> ManualIndex:
    index = ManualIndex(source_path=pdf_path, index_path=index_path)
    if index_path.is_file():
        index.load()
    else:
        index.build()
    return index


@sources_app.command("list")
def sources_list() -> None:
    """List source metadata already recorded in the local knowledge store."""
    _json_output({"sources": [source.model_dump(mode="json") for source in KnowledgeStore().list_research_sources()]})


@manual_app.command("index")
def manual_index(
    pdf_path: Path = typer.Option(DEFAULT_MANUAL_PATH, exists=True, readable=True),
    index_path: Path = typer.Option(DEFAULT_MANUAL_INDEX),
) -> None:
    """Build a deterministic, regenerable local lexical index from the source PDF."""
    index = ManualIndex(source_path=pdf_path, index_path=index_path)
    source = index.build()
    KnowledgeStore().store_research_source(source)
    _json_output({"source": source.model_dump(mode="json"), "index_path": str(index_path), "chunks": len(index.chunks)})


@manual_app.command("search")
def manual_search(
    query: str = typer.Argument(..., help="Lexical manual query"),
    limit: int = typer.Option(10, min=1, max=50),
    pdf_path: Path = typer.Option(DEFAULT_MANUAL_PATH, exists=True, readable=True),
    index_path: Path = typer.Option(DEFAULT_MANUAL_INDEX),
) -> None:
    """Search source text only; results are not verification evidence."""
    index = _load_manual_index(pdf_path, index_path)
    KnowledgeStore().store_research_source(index.source)
    _json_output({"query": query, "source": index.source.model_dump(mode="json"), "results": index.search(query, limit=limit)})


@manual_app.command("hypothesize")
def manual_hypothesize(
    query: str = typer.Argument(..., help="Manual text to search"),
    concept: str = typer.Argument(..., help="Unverified semantic concept"),
    hypothesis_id: str = typer.Argument(..., help="Stable hypothesis id"),
    claim: str = typer.Argument(..., help="Careful, human-reviewed manual claim"),
    confidence: float = typer.Option(0.5, min=0.0, max=1.0),
    pdf_path: Path = typer.Option(DEFAULT_MANUAL_PATH, exists=True, readable=True),
    index_path: Path = typer.Option(DEFAULT_MANUAL_INDEX),
) -> None:
    """Record manual provenance and a hypothesis. It never promotes verified knowledge."""
    index = _load_manual_index(pdf_path, index_path)
    results = index.search(query, limit=1)
    if not results:
        _json_output({"error": "no_manual_match", "query": query})
        raise typer.Exit(code=1)
    store = KnowledgeStore()
    store.store_research_source(index.source)
    result = results[0]
    evidence = ResearchEvidence(
        evidence_id=f"manual_{uuid4().hex}", source_id=index.source.id, page=result["page"],
        section=result["heading"], excerpt=result["excerpt"], claim=claim,
        related_concepts=[concept], confidence=confidence,
    )
    store.store_research_evidence(evidence)
    if store.get_hypothesis(hypothesis_id) is None:
        store.store_hypothesis(Hypothesis(
            hypothesis_id=hypothesis_id, target_capability=concept,
            semantic_guess=claim, confidence=confidence,
        ))
    hypothesis = store.attach_research_evidence(hypothesis_id, evidence.evidence_id)
    _json_output({"hypothesis": hypothesis.model_dump(mode="json"), "research_evidence": evidence.model_dump(mode="json"), "concept": store.get_concept(concept).model_dump(mode="json")})


def _human_research_plan(payload: dict) -> str:
    plan = payload["plan"]
    audit = payload["audit"]
    experiment = plan.get("proposed_experiment")
    lines = [
        f"Research goal: {plan['goal']}",
        f"Scope: {plan['interpreted_scope']}",
        "VERIFIED: " + (", ".join(plan["known_verified"]) or "none"),
        "MANUAL-SUPPORTED: " + (", ".join(plan["manual_supported"]) or "none"),
        "HYPOTHESES: " + (", ".join(plan["hypotheses"]) or "none"),
        "UNKNOWN / GAPS: " + ("; ".join(plan["unknowns"]) or "none"),
        f"RECOMMENDED NEXT TARGET: {plan['recommended_next_target']}",
        f"WHY: {plan['reasoning_summary']}",
        f"RESEARCH STEP: {plan['research_step_type']}",
        "PROPOSED EXPERIMENT: " + (f"{experiment['experiment_status']} — {experiment['reason']}" if experiment else "none"),
        f"HUMAN INPUT: {'required — ' + (plan['human_question'] or '') if plan['needs_human_input'] else 'not required'}",
        f"Audit: prompt={audit['prompt_version']}; provider={audit['provider']}; model={audit['model']}; dry-run=true",
    ]
    return "\n".join(lines)


@research_app.command("plan")
def research_plan(
    goal: str = typer.Argument(..., help="Human research goal; this command is always dry-run only"),
    output_path: Path | None = typer.Option(None, help="Optional JSON audit output path"),
    json_output: bool = typer.Option(False, "--json", help="Print the structured plan/audit as JSON"),
    model: str | None = typer.Option(None, help="Optional OpenAI model override; defaults to WINWATT_RESEARCH_MODEL or gpt-5.6-sol"),
) -> None:
    """Retrieve local evidence and ask an LLM for a validated plan. Never executes WinWatt."""
    try:
        index = _load_manual_index(DEFAULT_MANUAL_PATH, DEFAULT_MANUAL_INDEX)
        store = KnowledgeStore()
        result = ResearchPlanner(OpenAIProvider(model=model), store, index).plan(goal)
    except ResearchPlanValidationError as exc:
        payload = exc.failure.model_dump(mode="json")
        if output_path is not None:
            saved = ResearchPlanner.save_failure(exc.failure, output_path.resolve())
            payload["audit_path"] = str(saved)
        _json_output(payload)
        raise typer.Exit(code=1)
    except RuntimeError as exc:
        _json_output({"error": "research_planner_unavailable", "message": str(exc), "dry_run": True})
        raise typer.Exit(code=2)
    payload = result.model_dump(mode="json")
    if output_path is not None:
        saved = ResearchPlanner.save_audit(result, output_path.resolve())
        payload["audit_path"] = str(saved)
    if json_output:
        _json_output(payload)
    else:
        typer.echo(_human_research_plan(payload))


@research_app.command("run")
def research_run(
    goal: str = typer.Argument(..., help="Natural-language research goal"),
    source_project: Path = typer.Option(Path("tests/testwwp.wwp"), "--project", exists=True, readable=True),
    output_dir: Path = typer.Option(Path("data/runtime_maps/research_sessions")),
    hint: list[str] = typer.Option([], "--hint", help="Non-verified human research lead; repeatable"),
    json_output: bool = typer.Option(False, "--json"),
) -> None:
    """Run one bounded sandbox research session; never exposes raw desktop controls."""
    if os.environ.get("WINWATT_E2E") != "1":
        _json_output({"error": "e2e_disabled", "hint": "Set WINWATT_E2E=1 to permit a sandbox research session."})
        raise typer.Exit(code=2)
    output_dir = output_dir.resolve()
    index = _load_manual_index(DEFAULT_MANUAL_PATH, DEFAULT_MANUAL_INDEX)
    store = KnowledgeStore()
    planner = ResearchPlanner(OpenAIProvider(), store, index)
    orchestrator = ResearchOrchestrator(
        planner, store,
        discovery_factory=lambda: ResearchDiscoveryRunner(LiveRoomBoundaryDiscoveryUI(output_dir), store=store),
        experiment_runner=ExperimentRunner(output_dir=output_dir / "experiments"),
    )
    result = orchestrator.run(goal, source_project=source_project.resolve(), output_dir=output_dir, budget=ResearchBudget(max_iterations=int(os.environ.get("WINWATT_RESEARCH_MAX_ITERATIONS", "12")), max_seconds=int(os.environ.get("WINWATT_RESEARCH_MAX_SECONDS", "1800"))), human_hints=hint)
    path = output_dir / result.session_id / "research_session.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(result.model_dump_json(indent=2) + "\n", encoding="utf-8")
    payload = {**result.model_dump(mode="json"), "audit_path": str(path)}
    if json_output:
        _json_output(payload)
    else:
        typer.echo(json.dumps(payload, ensure_ascii=False, indent=2))


@discover_app.command("room-boundary-types")
def discover_room_boundary_types(
    source_project: Path = typer.Option(Path("tests/testwwp.wwp"), exists=True, readable=True, help="Source project copied to a sandbox"),
    room_name: str = typer.Option("Discovery room"),
    output_dir: Path = typer.Option(Path("data/runtime_maps/discovery")),
    max_ui_actions: int = typer.Option(24, min=1, max=80),
    max_seconds: int = typer.Option(90, min=5, max=300),
    json_output: bool = typer.Option(False, "--json"),
) -> None:
    """Enumerate room-boundary types in a disposable sandbox; never verifies a capability."""
    if os.environ.get("WINWATT_E2E") != "1":
        _json_output({"error": "e2e_disabled", "hint": "Set WINWATT_E2E=1 to permit bounded sandbox UI discovery."})
        raise typer.Exit(code=2)
    source = source_project.resolve()
    runner = ResearchDiscoveryRunner(
        LiveRoomBoundaryDiscoveryUI(output_dir.resolve()), store=KnowledgeStore(),
    )
    result = runner.run(DiscoveryGoal(
        operation="enumerate_room_boundary_structure_types", source_project=str(source), room_name=room_name,
        max_ui_actions=max_ui_actions, max_seconds=max_seconds,
    ))
    result_path = output_dir.resolve() / result.session_id / "discovery_result.json"
    result_path.parent.mkdir(parents=True, exist_ok=True)
    result_path.write_text(result.model_dump_json(indent=2) + "\n", encoding="utf-8")
    payload = {**result.model_dump(mode="json"), "result_path": str(result_path)}
    if json_output:
        _json_output(payload)
    else:
        typer.echo(json.dumps(payload, ensure_ascii=False, indent=2))
    if result.errors:
        raise typer.Exit(code=1)


@discover_app.command("classify-room-boundary-structures")
def classify_room_boundary_structures(
    source_project: Path = typer.Option(Path("tests/testwwp.wwp"), exists=True, readable=True, help="Source project copied to a sandbox"),
    room_name: str = typer.Option("Discovery room"),
    output_dir: Path = typer.Option(Path("data/runtime_maps/discovery")),
    reference: list[str] = typer.Option([], "--reference", help="Observed catalogue caption to inspect; repeat at most six times"),
    max_representatives: int = typer.Option(6, min=1, max=6),
    max_ui_actions: int = typer.Option(40, min=1, max=40),
    max_seconds: int = typer.Option(180, min=5, max=180),
    json_output: bool = typer.Option(False, "--json"),
) -> None:
    """Classify concrete catalogue references from bounded, cancelled detail inspection only."""
    if os.environ.get("WINWATT_E2E") != "1":
        _json_output({"error": "e2e_disabled", "hint": "Set WINWATT_E2E=1 to permit bounded sandbox UI discovery."})
        raise typer.Exit(code=2)
    output_dir = output_dir.resolve()
    runner = ResearchDiscoveryRunner(LiveRoomBoundaryDiscoveryUI(output_dir), store=KnowledgeStore())
    result = runner.classify_room_boundary_structures(StructureClassificationGoal(
        source_project=str(source_project.resolve()), room_name=room_name, max_representatives=max_representatives,
        representative_captions=reference, max_ui_actions=max_ui_actions, max_seconds=max_seconds,
    ))
    result_path = output_dir / result.session_id / "classification_result.json"
    result_path.parent.mkdir(parents=True, exist_ok=True)
    result_path.write_text(result.model_dump_json(indent=2) + "\n", encoding="utf-8")
    payload = {**result.model_dump(mode="json"), "result_path": str(result_path)}
    if json_output:
        _json_output(payload)
    else:
        typer.echo(json.dumps(payload, ensure_ascii=False, indent=2))
    if result.errors:
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
