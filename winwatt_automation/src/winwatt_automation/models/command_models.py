from pydantic import BaseModel


class CommandDefinition(BaseModel):
    command_name: str
    source_form: str
    source_item_name: str
    source_item_type: str
    caption: str | None = None
    semantic_role: str | None = None
