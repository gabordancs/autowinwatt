from __future__ import annotations

from winwatt_automation.models.command_models import CommandDefinition
from winwatt_automation.models.ui_models import UIModel
from winwatt_automation.parser.normalizer import normalize_identifier


class CommandRegistry:
    def __init__(self) -> None:
        self._commands: list[CommandDefinition] = []

    @property
    def commands(self) -> list[CommandDefinition]:
        return list(self._commands)

    def build_from_ui_model(self, ui_model: UIModel) -> None:
        self._commands.clear()
        for form in ui_model.forms:
            for item in form.items:
                if item.semantic_role != "action":
                    continue
                command_name = normalize_identifier(item.name) or "unnamed_command"
                self._commands.append(
                    CommandDefinition(
                        command_name=command_name,
                        source_form=form.name,
                        source_item_name=item.name,
                        source_item_type=item.item_type,
                        caption=item.properties.get("Caption"),
                        semantic_role=item.semantic_role,
                    )
                )

    def find_by_name(self, name: str) -> list[CommandDefinition]:
        term = normalize_identifier(name) or name
        return [cmd for cmd in self._commands if cmd.command_name == term]

    def find_by_form(self, form: str) -> list[CommandDefinition]:
        return [cmd for cmd in self._commands if cmd.source_form == form]

    def find_by_caption(self, caption: str) -> list[CommandDefinition]:
        return [cmd for cmd in self._commands if (cmd.caption or "").lower() == caption.lower()]

    def find_by_item_type(self, item_type: str) -> list[CommandDefinition]:
        return [cmd for cmd in self._commands if cmd.source_item_type == item_type]
