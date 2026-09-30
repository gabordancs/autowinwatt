from winwatt_automation.agent.capabilities import CertificationToolRegistry
from winwatt_automation.knowledge.certification import (
    load_certification_knowledge,
    missing_evidence_paths,
)


def test_certification_knowledge_is_evidence_backed() -> None:
    knowledge = load_certification_knowledge()

    assert knowledge.profile_id == "winwatt_8c137b67c0a2214bb91aeae8"
    assert not missing_evidence_paths(knowledge)
    assert knowledge.fact("workflow.heating_fixture").status == "verified"


def test_verified_fact_tool_ids_exist_and_are_executable() -> None:
    knowledge = load_certification_knowledge()
    registry = CertificationToolRegistry.load()

    for fact in knowledge.facts:
        for tool_id in fact.tool_ids:
            tool = registry.require_executable(tool_id, profile_id=knowledge.profile_id)
            assert tool.status == "verified"
