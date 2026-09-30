"""Version-bound tool registry for deterministic WinWatt operations.

The registry is deliberately smaller than the mapping corpus.  Observations
remain visible to planning code, but only save/reopen verified entries may be
resolved as executable tools.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Literal

from pydantic import BaseModel, Field, model_validator


PACKAGE_ROOT = Path(__file__).resolve().parents[3]
DEFAULT_REGISTRY_PATH = PACKAGE_ROOT / "data" / "capabilities" / "certification_tools.json"


class ToolEvidence(BaseModel):
    kind: Literal["observation", "save_reopen", "validation"]
    path: str = Field(min_length=1)
    deterministic: bool = False
    assertion: str = Field(min_length=1)


class CertificationTool(BaseModel):
    tool_id: str = Field(min_length=1)
    version: str = Field(pattern=r"^\d+\.\d+\.\d+$")
    status: Literal["observed", "verified", "rejected"]
    description: str = Field(min_length=1)
    profile_ids: list[str] = Field(min_length=1)
    handler: str | None = None
    safety_scope: Literal["read_only", "sandbox_copy", "local_files"]
    mutates_project: bool = False
    input_contract: dict[str, str] = Field(default_factory=dict)
    output_contract: dict[str, str] = Field(default_factory=dict)
    preconditions: list[str] = Field(default_factory=list)
    postconditions: list[str] = Field(default_factory=list)
    retry_policy: str = "no_automatic_retry"
    idempotency: str = "not_idempotent"
    evidence: list[ToolEvidence] = Field(default_factory=list)

    @model_validator(mode="after")
    def verified_tool_has_execution_proof(self) -> "CertificationTool":
        if self.status != "verified":
            return self
        if not self.handler:
            raise ValueError("verified tool requires a handler")
        if not self.postconditions:
            raise ValueError("verified tool requires machine-checkable postconditions")
        required_evidence = "validation" if self.safety_scope == "local_files" else "save_reopen"
        if not any(item.kind == required_evidence and item.deterministic for item in self.evidence):
            raise ValueError(f"verified tool requires deterministic {required_evidence} evidence")
        return self

    @property
    def executable(self) -> bool:
        return self.status == "verified" and self.handler is not None


class CertificationToolRegistry:
    """Load and gate the tools that an agent is allowed to execute."""

    def __init__(self, tools: list[CertificationTool], *, schema_version: int = 1) -> None:
        self.schema_version = schema_version
        self._tools = {tool.tool_id: tool for tool in tools}
        if len(self._tools) != len(tools):
            raise ValueError("duplicate certification tool_id")

    @classmethod
    def load(cls, path: Path = DEFAULT_REGISTRY_PATH) -> "CertificationToolRegistry":
        payload = json.loads(path.read_text(encoding="utf-8"))
        return cls(
            [CertificationTool.model_validate(item) for item in payload.get("tools", [])],
            schema_version=int(payload.get("schema_version", 1)),
        )

    def get(self, tool_id: str) -> CertificationTool | None:
        return self._tools.get(tool_id)

    def list(self, *, include_observed: bool = True) -> list[CertificationTool]:
        tools = self._tools.values()
        if not include_observed:
            tools = (tool for tool in tools if tool.executable)
        return sorted(tools, key=lambda item: item.tool_id)

    def require_executable(self, tool_id: str, *, profile_id: str) -> CertificationTool:
        tool = self.get(tool_id)
        if tool is None:
            raise KeyError(f"unknown certification tool: {tool_id}")
        if not tool.executable:
            raise PermissionError(f"certification tool is not verified: {tool_id}")
        if profile_id not in tool.profile_ids:
            raise PermissionError(
                f"certification tool {tool_id} is not verified for profile {profile_id}"
            )
        return tool

    def agent_view(self, *, profile_id: str) -> list[dict[str, Any]]:
        """Return only callable, profile-compatible contracts for an agent."""
        return [
            tool.model_dump(mode="json") | {"executable": True}
            for tool in self.list(include_observed=False)
            if profile_id in tool.profile_ids
        ]
