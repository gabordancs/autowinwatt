from __future__ import annotations

from pathlib import Path

from lxml import etree

from winwatt_automation.models.ui_models import UIForm, UIItem, UIModel

IMPORTANT_PROPERTIES = {"Caption", "Hint", "Filter", "Text", "Items", "Name", "Type"}


class UIParseError(Exception):
    """Raised when Hungarian.xml cannot be parsed into a valid UI model."""


def _extract_properties(node: etree._Element) -> dict[str, str]:
    props: dict[str, str] = {}
    for prop in node.xpath("./Properties/Property"):
        prop_name = prop.attrib.get("Name")
        prop_value = prop.attrib.get("Value")
        if prop_name and prop_name in IMPORTANT_PROPERTIES and prop_value is not None:
            props[prop_name] = prop_value
    return props


def _extract_items(container: etree._Element) -> list[UIItem]:
    items: list[UIItem] = []
    for item in container.xpath("./Items/Item"):
        name = item.attrib.get("Name") or "UnnamedItem"
        item_type = item.attrib.get("Type") or "UnknownType"
        properties = _extract_properties(item)
        items.append(UIItem(name=name, item_type=item_type, properties=properties))
    return items


def parse_hungarian_xml(xml_path: str | Path) -> UIModel:
    path = Path(xml_path)
    if not path.exists():
        raise UIParseError(f"XML file does not exist: {path}")

    try:
        root = etree.parse(str(path)).getroot()
    except etree.XMLSyntaxError as exc:
        raise UIParseError(f"Invalid XML format in {path}") from exc

    forms: list[UIForm] = []

    for form in root.xpath(".//Forms/Form"):
        form_name = form.attrib.get("Name") or "UnnamedForm"
        form_type = form.attrib.get("Type") or "UnknownFormType"
        form_properties = _extract_properties(form)
        items = _extract_items(form)
        forms.append(
            UIForm(
                name=form_name,
                form_type=form_type,
                caption=form_properties.get("Caption"),
                items=items,
            )
        )

    action_items = []
    for action in root.xpath(".//Actions/Action"):
        name = action.attrib.get("Name") or "UnnamedAction"
        item_type = action.attrib.get("Type") or "TAction"
        action_items.append(UIItem(name=name, item_type=item_type, properties=_extract_properties(action)))

    menu_items = []
    for menu in root.xpath(".//MenuItems/MenuItem"):
        name = menu.attrib.get("Name") or "UnnamedMenuItem"
        item_type = menu.attrib.get("Type") or "TMenuItem"
        menu_items.append(UIItem(name=name, item_type=item_type, properties=_extract_properties(menu)))

    if action_items:
        forms.append(UIForm(name="__Actions__", form_type="Virtual", caption="Actions", items=action_items))
    if menu_items:
        forms.append(UIForm(name="__MenuItems__", form_type="Virtual", caption="MenuItems", items=menu_items))

    return UIModel(forms=forms)
