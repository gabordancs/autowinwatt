from winwatt_automation.planner.models import CandidateResearchPlan


def test_candidate_research_plan_schema_is_strict_for_every_object() -> None:
    schema = CandidateResearchPlan.model_json_schema()

    def walk(node):
        if isinstance(node, dict):
            if node.get("type") == "object":
                assert node.get("additionalProperties") is False, node
            for value in node.values():
                walk(value)
        elif isinstance(node, list):
            for value in node:
                walk(value)

    walk(schema)
