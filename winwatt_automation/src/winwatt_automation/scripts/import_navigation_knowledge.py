from __future__ import annotations

import json
from pathlib import Path

from winwatt_automation.navigation.importer import import_legacy_navigation
from winwatt_automation.navigation.store import NavigationKnowledgeStore


def main() -> None:
    root = Path(__file__).resolve().parents[3]
    store = NavigationKnowledgeStore()
    report = import_legacy_navigation(root, store)
    print(json.dumps({"store_path": str(store.path), **report.model_dump(), "states": len(store.states()), "transitions": len(store.transitions())}, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
