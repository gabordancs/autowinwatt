from __future__ import annotations

from pydantic import BaseModel, Field


class UIProperty(BaseModel):
    id: str
    value: str | None = None


class UIItem(BaseModel):
    name: str
    item_type: str
    properties: dict[str, str] = Field(default_factory=dict)
    semantic_role: str | None = None
    normalized_name: str | None = None
    normalized_caption: str | None = None
    stable_key: str | None = None


class UIForm(BaseModel):
    name: str
    form_type: str
    caption: str | None = None
    items: list[UIItem] = Field(default_factory=list)


class UIModel(BaseModel):
    forms: list[UIForm] = Field(default_factory=list)
