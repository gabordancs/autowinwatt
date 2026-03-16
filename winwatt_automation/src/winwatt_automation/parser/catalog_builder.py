from __future__ import annotations

from collections import defaultdict
from typing import Any

from winwatt_automation.models.ui_models import UIForm, UIItem, UIModel
from winwatt_automation.parser.normalizer import normalize_identifier

ACTION_TYPES = {"TAction", "TMenuItem", "TToolButton", "TButton"}
INPUT_TYPES = {"TEdit", "TComboBox", "TCheckBox", "TRadioButton", "TMemo", "TMaskEdit", "TSpinEdit"}
MENU_TYPES = {"TMainMenu", "TPopupMenu", "TMenuItem"}
FILE_DIALOG_TYPES = {"TOpenDialog", "TSaveDialog"}
TAB_TYPES = {"TTabSheet", "TPageControl"}
LIST_TYPES = {"TListView", "TStringGrid", "TTreeView", "TListBox"}

DIALOG_BUTTON_HINTS = {"ok", "cancel", "mégse", "help", "close", "yes", "no", "apply"}


def _item_caption(item: UIItem) -> str | None:
    return item.properties.get("Caption") or item.properties.get("Text")


def _score_action_relevance(item: UIItem) -> int:
    name = (item.name or "").lower()
    text = " ".join(
        [
            item.name,
            item.properties.get("Caption", ""),
            item.properties.get("Hint", ""),
        ]
    ).lower()
    if any(term in text for term in ("open", "save", "projekt", "project", "print", "export", "option", "beáll")):
        return 90
    if item.item_type in {"TAction", "TMenuItem"}:
        return 70
    if item.item_type in {"TToolButton", "TButton"}:
        return 55
    if "new" in name:
        return 60
    return 35


def _is_dialog_button(item: UIItem) -> bool:
    caption = (_item_caption(item) or "").strip().lower()
    return item.item_type == "TButton" and (caption in DIALOG_BUTTON_HINTS or item.name.lower().endswith("button"))


def _form_key(form: UIForm) -> str:
    return normalize_identifier(form.name) or form.name.lower()


def _menu_parent_name(item: UIItem) -> str | None:
    return item.properties.get("Parent") or item.properties.get("ParentName") or item.properties.get("Menu")


def build_forms_catalog(ui_model: UIModel) -> list[dict[str, Any]]:
    forms: list[dict[str, Any]] = []
    for form in ui_model.forms:
        item_types = [item.item_type for item in form.items]
        buttons = sum(1 for t in item_types if t == "TButton")
        menus = sum(1 for t in item_types if t in MENU_TYPES)
        tabs = sum(1 for t in item_types if t in TAB_TYPES)
        lists = sum(1 for t in item_types if t in LIST_TYPES)
        inputs = sum(1 for t in item_types if t in INPUT_TYPES)
        actions = sum(1 for item in form.items if item.item_type in ACTION_TYPES or item.semantic_role == "action")
        form_name_l = form.name.lower()

        dialog_candidate = (
            any(_is_dialog_button(item) for item in form.items)
            or any(item.item_type in FILE_DIALOG_TYPES for item in form.items)
            or any(token in form_name_l for token in ("modify", "option", "dialog", "print", "export"))
        )
        main_candidate = form.name == "MainForm" or "main" in form_name_l or "frame" in form_name_l

        forms.append(
            {
                "form_name": form.name,
                "form_type": form.form_type,
                "form_caption": form.caption,
                "stable_key": _form_key(form),
                "item_count": len(form.items),
                "action_count": actions,
                "button_count": buttons,
                "menu_count": menus,
                "tab_count": tabs,
                "list_count": lists,
                "input_count": inputs,
                "is_dialog_candidate": dialog_candidate,
                "is_main_window_candidate": main_candidate,
            }
        )
    return forms


def build_controls_catalog(ui_model: UIModel) -> list[dict[str, Any]]:
    controls: list[dict[str, Any]] = []
    for form in ui_model.forms:
        for item in form.items:
            caption = item.properties.get("Caption")
            controls.append(
                {
                    "form_name": form.name,
                    "item_name": item.name,
                    "item_type": item.item_type,
                    "semantic_role": item.semantic_role,
                    "caption": caption,
                    "hint": item.properties.get("Hint"),
                    "text": item.properties.get("Text"),
                    "filter": item.properties.get("Filter"),
                    "normalized_name": item.normalized_name or normalize_identifier(item.name),
                    "normalized_caption": item.normalized_caption or normalize_identifier(caption),
                    "stable_key": item.stable_key or f"{form.name}.{item.name}",
                    "parent_form": form.name,
                    "is_action_candidate": item.item_type in ACTION_TYPES or item.semantic_role == "action",
                    "is_input_candidate": item.item_type in INPUT_TYPES or item.semantic_role == "input",
                    "is_menu_candidate": item.item_type in MENU_TYPES,
                    "is_dialog_button_candidate": _is_dialog_button(item),
                }
            )
    return controls


def build_actions_catalog(ui_model: UIModel) -> list[dict[str, Any]]:
    actions: list[dict[str, Any]] = []
    for form in ui_model.forms:
        for item in form.items:
            if item.item_type not in ACTION_TYPES and item.semantic_role != "action":
                continue
            if item.item_type == "TAction":
                source_kind = "action"
            elif item.item_type == "TMenuItem":
                source_kind = "menu_item"
            elif item.item_type == "TToolButton":
                source_kind = "toolbar_item"
            else:
                source_kind = "button"

            actions.append(
                {
                    "form_name": form.name,
                    "item_name": item.name,
                    "item_type": item.item_type,
                    "caption": item.properties.get("Caption"),
                    "hint": item.properties.get("Hint"),
                    "normalized_command_name": normalize_identifier(item.name),
                    "stable_key": item.stable_key or f"{form.name}.{item.name}",
                    "source_kind": source_kind,
                    "workflow_relevance_score": _score_action_relevance(item),
                }
            )
    return actions


def build_menu_tree(ui_model: UIModel) -> dict[str, Any]:
    menu_forms: dict[str, dict[str, Any]] = {}

    for form in ui_model.forms:
        menu_items = [item for item in form.items if item.item_type == "TMenuItem"]
        if not menu_items:
            continue

        by_name = {item.name: item for item in menu_items}
        children_by_parent: dict[str, list[UIItem]] = defaultdict(list)
        top_level: list[UIItem] = []

        for item in menu_items:
            parent_name = _menu_parent_name(item)
            if parent_name and parent_name in by_name:
                children_by_parent[parent_name].append(item)
            else:
                top_level.append(item)

        def build_node(menu_item: UIItem) -> dict[str, Any]:
            return {
                "name": menu_item.name,
                "caption": menu_item.properties.get("Caption"),
                "item_type": menu_item.item_type,
                "stable_key": menu_item.stable_key or f"{form.name}.{menu_item.name}",
                "children": [build_node(child) for child in children_by_parent.get(menu_item.name, [])],
            }

        menu_forms[form.name] = {
            "form_name": form.name,
            "menu_bar": [build_node(item) for item in top_level],
        }

    return menu_forms


def build_dialog_catalog(ui_model: UIModel) -> list[dict[str, Any]]:
    dialogs: list[dict[str, Any]] = []
    for form in ui_model.forms:
        buttons = [item for item in form.items if _is_dialog_button(item)]
        inputs = [item for item in form.items if item.item_type in INPUT_TYPES or item.semantic_role == "input"]
        files = [item for item in form.items if item.item_type in FILE_DIALOG_TYPES]
        tabs = [item for item in form.items if item.item_type in TAB_TYPES]

        name_l = form.name.lower()
        if not (buttons or files or any(t in name_l for t in ("modify", "options", "dialog", "print", "export"))):
            continue

        if files:
            dialog_type_guess = "file_dialog"
            likely_purpose = "file_selection"
        elif "modify" in name_l:
            dialog_type_guess = "modify_dialog"
            likely_purpose = "modify_data"
        elif "option" in name_l:
            dialog_type_guess = "options_dialog"
            likely_purpose = "program_options"
        elif "print" in name_l or "export" in name_l:
            dialog_type_guess = "output_dialog"
            likely_purpose = "print_or_export"
        else:
            dialog_type_guess = "confirmation_or_data_entry"
            likely_purpose = "confirm_or_enter_values"

        dialogs.append(
            {
                "form_name": form.name,
                "form_caption": form.caption,
                "dialog_type_guess": dialog_type_guess,
                "buttons": [b.name for b in buttons],
                "inputs": [i.name for i in inputs],
                "file_dialogs": [f.name for f in files],
                "tabs": [t.name for t in tabs],
                "likely_purpose": likely_purpose,
            }
        )
    return dialogs


def build_workflow_seeds(ui_model: UIModel) -> list[dict[str, Any]]:
    seeds: list[dict[str, Any]] = []
    for form in ui_model.forms:
        for item in form.items:
            combined = " ".join([item.name, item.properties.get("Caption", ""), item.properties.get("Hint", "")]).lower()
            workflow_name: str | None = None
            purpose: str | None = None
            next_form = "unknown"
            confidence = 0.4

            if "open" in combined and ("project" in combined or "projekt" in combined):
                workflow_name = "open_project"
                purpose = "open_existing_project"
                confidence = 0.95
            elif "save" in combined and ("project" in combined or "projekt" in combined):
                if "as" in combined:
                    workflow_name = "save_project_as"
                    purpose = "save_project_under_new_name"
                else:
                    workflow_name = "save_project"
                    purpose = "persist_current_project"
                confidence = 0.95
            elif "print" in combined:
                workflow_name = "print"
                purpose = "print_output"
                confidence = 0.8
            elif "export" in combined:
                workflow_name = "export"
                purpose = "export_output"
                confidence = 0.8
            elif "option" in combined:
                workflow_name = "program_options"
                purpose = "adjust_application_options"
                confidence = 0.75

            if workflow_name:
                seeds.append(
                    {
                        "workflow_name": workflow_name,
                        "entry_form": form.name,
                        "trigger_item_name": item.name,
                        "trigger_caption": item.properties.get("Caption"),
                        "trigger_stable_key": item.stable_key or f"{form.name}.{item.name}",
                        "expected_next_form_guess": next_form,
                        "purpose": purpose,
                        "confidence": confidence,
                    }
                )

    dedup: dict[tuple[str, str], dict[str, Any]] = {}
    for seed in seeds:
        key = (seed["workflow_name"], seed["trigger_stable_key"])
        dedup[key] = seed
    return list(dedup.values())


def build_static_runtime_map(ui_model: UIModel) -> list[dict[str, Any]]:
    mapping: list[dict[str, Any]] = []
    for form in ui_model.forms:
        for item in form.items:
            important = item.item_type in ACTION_TYPES or item.item_type in INPUT_TYPES or item.item_type in MENU_TYPES
            if not important:
                continue
            mapping.append(
                {
                    "stable_key": item.stable_key or f"{form.name}.{item.name}",
                    "form_name": form.name,
                    "item_name": item.name,
                    "caption": item.properties.get("Caption"),
                    "item_type": item.item_type,
                    "runtime_locator_status": "unmapped",
                    "runtime_locator_candidates": [],
                    "notes": "placeholder for runtime UIA mapping",
                }
            )
    return mapping
