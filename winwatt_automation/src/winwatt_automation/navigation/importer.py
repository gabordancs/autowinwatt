"""Conservative import of legacy runtime observations into NavigationKnowledge.

Legacy files establish only observed states or transitions.  The one native
route migrated by :class:`NavigationKnowledgeStore` is separately verified.
"""
from __future__ import annotations

import hashlib
import json
from pathlib import Path

from pydantic import BaseModel

from .models import NavigationControlSummary
from .store import NavigationKnowledgeStore


class NavigationImportReport(BaseModel):
    source_files_scanned: int = 0
    states_imported: int = 0
    transitions_imported: int = 0
    duplicates_merged: int = 0
    provenance_retained: int = 0

    model_config = {"extra": "forbid"}


def _fingerprint(payload: object) -> str:
    canonical = json.dumps(payload, ensure_ascii=False, sort_keys=True, default=str)
    return hashlib.sha1(canonical.encode("utf-8")).hexdigest()[:20]


def _controls(raw: object) -> list[NavigationControlSummary]:
    if not isinstance(raw, list):
        return []
    controls: list[NavigationControlSummary] = []
    for item in raw[:200]:
        if not isinstance(item, dict):
            continue
        caption = str(item.get("caption") or item.get("name") or item.get("text") or "")
        control_type = str(item.get("control_type") or item.get("type") or item.get("class_name") or "Unknown")
        identity = str(item.get("identity") or item.get("control_id") or _fingerprint([caption, control_type, item.get("automation_id")]))
        controls.append(NavigationControlSummary(identity=identity, caption=caption, control_type=control_type, enabled=bool(item.get("enabled", True))))
    return controls


def _upsert_snapshot(store: NavigationKnowledgeStore, raw: dict, source: str, report: NavigationImportReport):
    snapshot = raw.get("snapshot") if isinstance(raw.get("snapshot"), dict) else raw
    fingerprint = str(snapshot.get("state_fingerprint") or raw.get("state_fingerprint") or _fingerprint({
        "state_id": raw.get("state_id"), "title": snapshot.get("title") or raw.get("active_mdi_title"),
        "class": snapshot.get("class_name") or raw.get("window_class"), "controls": snapshot.get("controls") or raw.get("controls", []),
    }))
    existed = store.has_fingerprint(fingerprint)
    state = store.upsert_state(
        fingerprint,
        str(snapshot.get("class_name") or raw.get("window_class") or "legacy_runtime_map"),
        str(snapshot.get("title") or raw.get("active_mdi_title") or raw.get("state_id") or "legacy runtime state"),
        _controls(snapshot.get("controls") or raw.get("controls")), source,
        mdi_title=raw.get("active_mdi_title"),
        semantic_context=str(raw.get("semantic_context") or raw.get("state_id") or ""),
    )
    if existed:
        report.duplicates_merged += 1
    else:
        report.states_imported += 1
    report.provenance_retained += len(state.provenance)
    return state


def import_legacy_navigation(root: Path, store: NavigationKnowledgeStore | None = None) -> NavigationImportReport:
    """Import actual mapper/session artifacts under a repository root.

    A transition is created only when a research iteration explicitly contains
    both before and after snapshots plus an executed action.
    """
    store = store or NavigationKnowledgeStore()
    report = NavigationImportReport()
    runtime_root = root / "data" / "runtime_maps"
    if not runtime_root.exists():
        return report
    with store.batch():
        for path in runtime_root.rglob("*.json"):
            report.source_files_scanned += 1
            try:
                raw = json.loads(path.read_text(encoding="utf-8"))
            except (OSError, json.JSONDecodeError):
                continue
            if path.name == "research_session.json" and isinstance(raw, dict):
                for iteration in raw.get("iterations", []):
                    if not isinstance(iteration, dict):
                        continue
                    for observation in iteration.get("observations", []):
                        if not isinstance(observation, dict) or not isinstance(observation.get("before"), dict) or not isinstance(observation.get("after"), dict):
                            continue
                        before = _upsert_snapshot(store, observation["before"], "research_session", report)
                        after = _upsert_snapshot(store, observation["after"], "research_session", report)
                        executed = observation.get("executed_action") if isinstance(observation.get("executed_action"), dict) else {}
                        store.upsert_transition(
                            before.id, str(executed.get("action_type") or executed.get("action") or "research_ui_action"), after.id,
                            action_identity=executed.get("control_identity") or executed.get("identity"),
                            semantic_action=str(iteration.get("selected_action", {}).get("semantic_context") or "legacy research UI transition"),
                            expected_state=after.fingerprint, status="observed",
                        )
                        report.transitions_imported += 1
                continue
            if isinstance(raw, dict) and ("state_id" in raw or "snapshot" in raw or "active_mdi_title" in raw):
                _upsert_snapshot(store, raw, "runtime_mapper", report)
    return report
