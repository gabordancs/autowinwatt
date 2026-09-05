from __future__ import annotations

import json
from pathlib import Path

import pytest

from winwatt_automation.knowledge.models import Hypothesis, KnowledgeStatus, SemanticCapability, SemanticConcept
from winwatt_automation.knowledge.store import KnowledgeStore
from winwatt_automation.planner.models import ResearchPlan
from winwatt_automation.planner.planner import ResearchPlanValidationError, ResearchPlanner
from winwatt_automation.planner.provider import OpenAIProvider
from winwatt_automation.research.manual_index import ManualIndex
from winwatt_automation.research.models import ResearchEvidence


class StubProvider:
    provider_name = "stub"
    model = "stub-research-model"

    def __init__(self, payload: dict) -> None:
        self.payload = payload
        self.calls: list[dict] = []

    def generate_structured(self, *, instructions: str, input_text: str, response_model: type[ResearchPlan]):
        self.calls.append({"instructions": instructions, "input": json.loads(input_text)})
        parsed = response_model.model_validate(self.payload)
        return parsed, {"mock": True, "output": parsed.model_dump(mode="json")}


def _planner_fixture(tmp_path: Path, payload: dict) -> tuple[ResearchPlanner, KnowledgeStore, StubProvider]:
    store = KnowledgeStore(path=tmp_path / "knowledge.json", capability_path=tmp_path / "none.json")
    verified = "room.boundary.external_wall.x_m"
    store._data["concepts"][verified] = SemanticConcept(
        concept=verified, entity="RoomBoundary", data_type="float", unit="m", status=KnowledgeStatus.VERIFIED, confidence=1.0,
    ).model_dump(mode="json")
    store._data["capabilities"][verified] = SemanticCapability(capability=verified, status=KnowledgeStatus.VERIFIED, roundtrip_verified=True).model_dump(mode="json")
    store._data["concepts"]["room.area_m2"] = SemanticConcept(
        concept="room.area_m2", entity="Room", data_type="float", unit="m2", status=KnowledgeStatus.VERIFIED, confidence=1.0,
    ).model_dump(mode="json")
    store._save()
    index = ManualIndex(tmp_path / "WinWatt.pdf", tmp_path / "manual.json")
    source = index.build_from_pages([
        "Helyiségek\nEgyéb, irreleváns szöveg.",
        "Külső fal\nKülső falszerkezetnél napsugárzási abszorpciós tényező adható meg.",
    ])
    store.store_research_source(source)
    target = "room.boundary.external_wall.solar_absorptance"
    store.store_hypothesis(Hypothesis(hypothesis_id="hyp_abs", target_capability=target, semantic_guess="manual interpretation", confidence=0.72))
    evidence = store.store_research_evidence(ResearchEvidence(
        evidence_id="manual_abs", source_id=source.id, page=2, section="Külső fal",
        excerpt="napsugárzási abszorpciós tényező", claim="manual claim", related_concepts=[target], confidence=0.72,
    ))
    store.attach_research_evidence("hyp_abs", evidence.evidence_id)
    provider = StubProvider(payload)
    return ResearchPlanner(provider, store, index), store, provider


def _valid_plan() -> dict:
    return {
        "goal": "Tanuld meg a külső falak kezelését",
        "interpreted_scope": "Room external-wall handling.",
        "known_verified": ["room.boundary.external_wall.x_m"],
        "manual_supported": ["room.boundary.external_wall.solar_absorptance (WinWatt.pdf p.2)"],
        "hypotheses": ["room.boundary.external_wall.solar_absorptance"],
        "unknowns": ["No safe read/write handler exists for solar absorptance."],
        "recommended_next_target": "room.boundary.external_wall.solar_absorptance",
        "reasoning_summary": "The manual supports it, but only X is runtime verified.",
        "research_step_type": "unsupported",
        "proposed_hypothesis": {"target_capability": "room.boundary.external_wall.solar_absorptance", "semantic_guess": "A field may represent solar absorptance.", "confidence": 0.72},
        "needs_human_input": False,
        "human_question": None,
    }


def test_planner_retrieves_relevant_context_and_keeps_manual_provenance(tmp_path: Path) -> None:
    planner, _, provider = _planner_fixture(tmp_path, _valid_plan())
    result = planner.plan("Tanuld meg a külső falak kezelését")

    assert [item.concept for item in result.audit.context.verified_concepts] == ["room.boundary.external_wall.x_m"]
    assert [item.concept for item in result.audit.context.hypotheses] == ["room.boundary.external_wall.solar_absorptance"]
    assert "room.area_m2" not in [item.concept for item in result.audit.context.relevant_capabilities]
    assert result.audit.context.manual_evidence[0].page == 2
    assert "abszorpciós" in result.audit.context.manual_evidence[0].excerpt
    assert provider.calls and provider.calls[0]["input"]["research_context"]["manual_evidence"][0]["page"] == 2
    assert 'allowed_verified_concepts = ["room.boundary.external_wall.x_m"]' in provider.calls[0]["instructions"]
    assert 'allowed_hypothesis_concepts = ["room.boundary.external_wall.solar_absorptance"]' in provider.calls[0]["instructions"]


def test_planner_is_dry_run_and_auditable(tmp_path: Path) -> None:
    planner, store, _ = _planner_fixture(tmp_path, _valid_plan())
    before = store.path.read_text(encoding="utf-8")
    result = planner.plan("Tanuld meg a külső falak kezelését")
    after = store.path.read_text(encoding="utf-8")
    saved = ResearchPlanner.save_audit(result, tmp_path / "plans" / "plan.json")

    assert before == after
    assert saved.is_file()
    assert result.audit.prompt_version == "research_planner_v0.1"
    assert result.plan.research_step_type == "unsupported"
    assert result.plan.proposed_experiment is None
    assert result.plan.needs_human_input is False


def test_planner_rejects_llm_attempt_to_claim_unverified_as_verified(tmp_path: Path) -> None:
    payload = _valid_plan()
    payload["known_verified"].append("room.boundary.external_wall")
    planner, _, _ = _planner_fixture(tmp_path, payload)
    with pytest.raises(ResearchPlanValidationError, match="not verified") as error:
        planner.plan("Tanuld meg a külső falak kezelését")
    diagnostic = error.value.failure
    assert "room.boundary.external_wall" in str(error.value)
    assert diagnostic.parsed_plan.known_verified == [
        "room.boundary.external_wall.x_m", "room.boundary.external_wall",
    ]
    assert [item.concept for item in diagnostic.audit.context.verified_concepts] == ["room.boundary.external_wall.x_m"]


def test_planner_rejects_unsupported_or_invalid_executable_experiment(tmp_path: Path) -> None:
    payload = _valid_plan()
    payload["research_step_type"] = "experiment"
    payload["proposed_experiment"] = {
        "experiment_status": "supported", "reason": "try raw UI", "spec": {
            "hypothesis_id": "hyp_abs", "target_capability": "room.boundary.external_wall.solar_absorptance",
            "change": {"entity": "room", "to": 0.7, "click": [1, 2]}, "observe": ["ui_readback"],
        },
    }
    planner, _, _ = _planner_fixture(tmp_path, payload)
    with pytest.raises(Exception, match="Extra inputs are not permitted"):
        planner.plan("Tanuld meg a külső falak kezelését")


def test_planner_audits_arbitrary_natural_language_observations_without_runner_access(tmp_path: Path) -> None:
    payload = _valid_plan()
    payload["research_step_type"] = "experiment"
    payload["proposed_experiment"] = {
        "experiment_status": "supported", "reason": "LLM proposal", "spec": {
            "hypothesis_id": "hyp_abs", "target_capability": "room.boundary.external_wall.x_m",
            "change": {"entity": "Room", "to": 2.0},
            "observe": ["A mentett érték megmarad-e a projekt újranyitása után."],
        },
    }
    planner, _, _ = _planner_fixture(tmp_path, payload)
    with pytest.raises(ResearchPlanValidationError, match="requested_observe_operations") as error:
        planner.plan("Tanuld meg a külső falak kezelését")
    failure = error.value.failure
    assert failure.parsed_plan is None
    assert failure.parsed_candidate_plan.proposed_experiment.spec.observe == [
        "A mentett érték megmarad-e a projekt újranyitása után."
    ]


def test_capability_enumeration_needs_no_experiment_and_preserves_discovery(tmp_path: Path) -> None:
    payload = _valid_plan()
    payload.update({
        "research_step_type": "capability_enumeration",
        "recommended_next_target": "room.boundary.attic_floor.structure_reference",
        "discovery": {
            "boundary_types": ["external wall", "attic floor"],
            "workflows": ["assign an existing structure"],
            "common_fields": ["type", "dimensions"],
            "type_specific_fields": [{"structure_type": "attic floor", "fields": ["structure reference"]}],
            "capability_candidates": ["room.boundary.attic_floor.structure_reference"],
        },
    })
    planner, _, _ = _planner_fixture(tmp_path, payload)
    result = planner.plan("Milyen típusú határoló szerkezeteket lehet egy helyiséghez felvenni?")
    assert result.plan.research_step_type == "capability_enumeration"
    assert result.plan.proposed_experiment is None
    assert result.plan.discovery.capability_candidates == ["room.boundary.attic_floor.structure_reference"]


def test_planner_allows_human_escalation(tmp_path: Path) -> None:
    payload = _valid_plan()
    payload["needs_human_input"] = True
    payload["human_question"] = "Which engineering interpretation should be tested first?"
    planner, _, _ = _planner_fixture(tmp_path, payload)
    result = planner.plan("Tanuld meg a külső falak kezelését")
    assert result.plan.needs_human_input is True
    assert result.plan.human_question


def test_planner_canonicalizes_rephrased_goal_without_relaxing_other_gates(tmp_path: Path) -> None:
    requested = "Tanuld meg, hogyan kell egy már létező Padlásfödém szerkezetet egy helyiség határoló szerkezeteként felvenni"
    payload = _valid_plan()
    payload["goal"] = "Tanuld meg, hogyan vehető fel egy már létező Padlásfödém szerkezet egy helyiség határoló szerkezeteként."
    payload["interpreted_scope"] = "Add an existing attic-floor structure as a room boundary."
    planner, _, provider = _planner_fixture(tmp_path, payload)

    result = planner.plan(requested)

    assert result.plan.goal == requested
    assert result.plan.interpreted_scope == "Add an existing attic-floor structure as a room boundary."
    assert provider.calls[0]["input"]["goal"] == requested
    assert "caller-supplied requested goal is authoritative" in provider.calls[0]["instructions"]


def test_openai_provider_without_key_fails_before_any_remote_or_ui_action(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    provider = OpenAIProvider()
    with pytest.raises(RuntimeError, match="OPENAI_API_KEY"):
        provider.generate_structured(instructions="x", input_text="{}", response_model=ResearchPlan)
