from pydantic import BaseModel, Field


class WorkflowStep(BaseModel):
    step: str
    action: str
    command: str | None = None
    expect_next_form: str | None = None


class WorkflowDefinition(BaseModel):
    name: str
    preconditions: list[str] = Field(default_factory=list)
    steps: list[WorkflowStep] = Field(default_factory=list)
    expected_forms: list[str] = Field(default_factory=list)
    success_conditions: list[str] = Field(default_factory=list)
    rollback: list[WorkflowStep] = Field(default_factory=list)
