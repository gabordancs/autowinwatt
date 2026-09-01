from __future__ import annotations

from pathlib import Path

from pydantic import BaseModel, Field, field_validator

from .room import RoomInput


class PrepareRoomsInput(BaseModel):
    """Input for the sandbox-only room preparation vertical slice."""

    project_path: Path
    rooms: list[RoomInput] = Field(min_length=1)

    @field_validator("rooms")
    @classmethod
    def unique_room_names(cls, rooms: list[RoomInput]) -> list[RoomInput]:
        names = [room.name.casefold() for room in rooms]
        if len(names) != len(set(names)):
            raise ValueError("room names must be unique")
        return rooms
