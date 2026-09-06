from __future__ import annotations

import os
from pathlib import Path
from typing import Any, Protocol, TypeVar

from pydantic import BaseModel
from dotenv import load_dotenv


ModelT = TypeVar("ModelT", bound=BaseModel)


class LLMProvider(Protocol):
    provider_name: str
    model: str

    def generate_structured(self, *, instructions: str, input_text: str, response_model: type[ModelT]) -> tuple[ModelT, dict[str, Any]]: ...


class OpenAIProvider:
    """Small adapter around the Responses API structured-output facility."""

    provider_name = "openai"

    def __init__(self, model: str | None = None, api_key: str | None = None) -> None:
        # Explicit bounded project paths; shell environment always wins.
        package_root = Path(__file__).resolve().parents[3]
        load_dotenv(package_root / ".env", override=False)
        load_dotenv(package_root.parent / ".env", override=False)
        self.model = model or os.environ.get("WINWATT_RESEARCH_MODEL", "gpt-5.6-sol")
        self._api_key = api_key or os.environ.get("OPENAI_API_KEY")

    def generate_structured(self, *, instructions: str, input_text: str, response_model: type[ModelT]) -> tuple[ModelT, dict[str, Any]]:
        if not self._api_key:
            raise RuntimeError("OpenAI research planner is not configured: set OPENAI_API_KEY. No WinWatt action was taken.")
        try:
            from openai import OpenAI
        except ImportError as exc:
            raise RuntimeError("OpenAI provider requires the 'openai' package. Install project dependencies first.") from exc
        client = OpenAI(api_key=self._api_key)
        response = client.responses.parse(
            model=self.model,
            instructions=instructions,
            input=input_text,
            text_format=response_model,
            store=False,
        )
        parsed = response.output_parsed
        if parsed is None:
            raise RuntimeError("OpenAI returned no structured research plan")
        return parsed, {"response_id": response.id, "output": parsed.model_dump(mode="json")}
