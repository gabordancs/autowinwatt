from winwatt_automation.models.ui_models import UIForm, UIItem, UIModel
from winwatt_automation.parser.normalizer import normalize_identifier

SEMANTIC_MAP = {
    "action": {"TButton", "TMenuItem", "TAction", "TToolButton"},
    "input": {"TEdit", "TComboBox", "TCheckBox", "TRadioButton"},
    "navigation": {"TTabSheet", "TPageControl"},
    "data_view": {"TListView", "TStringGrid"},
    "file_dialog": {"TOpenDialog", "TSaveDialog"},
    "context": {"TLabel", "TGroupBox"},
}


def classify_item(item: UIItem) -> UIItem:
    for role, types in SEMANTIC_MAP.items():
        if item.item_type in types:
            item.semantic_role = role
            break
    item.normalized_name = normalize_identifier(item.name)
    item.normalized_caption = normalize_identifier(item.properties.get("Caption"))
    return item


def assign_stable_key(form: UIForm, item: UIItem) -> UIItem:
    item.stable_key = f"{form.name}.{item.name}"
    return item


def classify_model(model: UIModel) -> UIModel:
    for form in model.forms:
        for item in form.items:
            classify_item(item)
            assign_stable_key(form, item)
    return model
