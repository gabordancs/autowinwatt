from winwatt_automation.models.workflow_models import WorkflowDefinition, WorkflowStep


def test_workflow_model_validation():
    workflow = WorkflowDefinition(
        name="open_project_dialog",
        preconditions=["application_connected"],
        steps=[WorkflowStep(step="open", action="click_command", command="open_project")],
        expected_forms=["OpenDialog"],
        success_conditions=["project_loaded"],
    )

    assert workflow.name == "open_project_dialog"
    assert workflow.steps[0].command == "open_project"
