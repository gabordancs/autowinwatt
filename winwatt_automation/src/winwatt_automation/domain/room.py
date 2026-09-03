from __future__ import annotations

from pydantic import BaseModel, Field, field_validator


class RoomInput(BaseModel):
    """A semantic room request; deliberately contains no UI implementation detail."""

    name: str = Field(min_length=1, max_length=120)
    area_m2: float | None = Field(default=None, gt=0)
    height_m: float | None = Field(default=None, gt=0)
    temperature_c: float | None = None
    summer_design_temperature_c: float | None = Field(default=None, gt=0)
    external_wall: bool = False

    @field_validator("name")
    @classmethod
    def normalize_name(cls, value: str) -> str:
        normalized = value.strip()
        if not normalized:
            raise ValueError("name must not be empty")
        return normalized
