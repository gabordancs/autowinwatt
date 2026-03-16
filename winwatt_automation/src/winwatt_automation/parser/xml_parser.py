from __future__ import annotations

from pathlib import Path

from lxml import etree

from winwatt_automation.models.ui_models import UIForm, UIItem, UIModel

IMPORTANT_PROPERTIES = {"Caption", "Hint", "Filter", "Text", "Items", "Name", "Type"}


class UIParseError(Exception):
    """Raised when Hungarian.xml cannot be parsed into a valid UI model."""


def _read_attr(node: etree._Element, *names: str) -> str | None:
    for name in names:
        value = node.attrib.get(name)
        if value is not None:
            return value
    return None


def _extract_properties(node: etree._Element) -> dict[str, str]:
    props: dict[str, str] = {}
    for prop in node.xpath("./property | ./Property | ./Properties/Property"):
        prop_name = _read_attr(prop, "id", "Id", "name", "Name")
        prop_value = _read_attr(prop, "value", "Value")
        if prop_name and prop_value is not None and prop_name in IMPORTANT_PROPERTIES:
            props[prop_name] = prop_value
    return props


def parse_hungarian_xml(xml_path: str | Path) -> UIModel:
    path = Path(xml_path)
    if not path.exists():
        raise UIParseError(f"XML file does not exist: {path}")

    try:
        root = etree.parse(str(path)).getroot()
    except etree.XMLSyntaxError as exc:
        raise UIParseError(f"Invalid XML format in {path}") from exc

    form_nodes = root.xpath("./form")
    print("root tag:", root.tag)
    print("form count:", len(form_nodes))
    print("first forms:", [f.get("name") for f in form_nodes[:3]])

    forms: list[UIForm] = []
    for form in form_nodes:
        form_name = _read_attr(form, "name", "Name") or "UnnamedForm"
        form_type = _read_attr(form, "type", "Type") or "UnknownFormType"
        form_properties = _extract_properties(form)

        items: list[UIItem] = []
        for item in form.xpath("./formitem"):
            item_name = _read_attr(item, "name", "Name") or "UnnamedItem"
            item_type = _read_attr(item, "type", "Type") or "UnknownType"
            item_properties = _extract_properties(item)
            items.append(UIItem(name=item_name, item_type=item_type, properties=item_properties))

        forms.append(
            UIForm(
                name=form_name,
                form_type=form_type,
                caption=form_properties.get("Caption"),
                items=items,
            )
        )

    return UIModel(forms=forms)
