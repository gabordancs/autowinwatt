"""Persistent, provenance-preserving index of all runtime mapping evidence.

This is deliberately an evidence/index layer, not a capability promotion
engine.  ``observed_mapping`` makes a UI graph observation reusable without
claiming that a production semantic capability is VERIFIED.
"""
from __future__ import annotations

import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


STATUS_UNEXPLORED = "UNEXPLORED"
STATUS_PARTIAL = "PARTIALLY_EXPLORED"
STATUS_KNOWN = "KNOWN"
STATUS_STALE = "KNOWN_STALE"
STATUS_BLOCKED = "BLOCKED"


def _id(prefix: str, *values: object) -> str:
    return f"{prefix}_{hashlib.sha1('|'.join(str(value) for value in values).encode()).hexdigest()[:16]}"


def _read(path: Path, default: Any) -> Any:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return default


class GlobalMappingStore:
    FILES = ("states.json", "transitions.json", "controls.json", "exploration_status.json", "provenance.json", "conflicts.json", "import_manifest.json", "ui_state_graph.json", "control_action_graph.json", "window_dialog_graph.json", "functional_operation_graph.json")

    def __init__(self, root: Path) -> None:
        self.root = root
        self.data = {name[:-5]: _read(root / name, {}) for name in self.FILES}
        self.data.setdefault("states", {}); self.data.setdefault("transitions", {}); self.data.setdefault("controls", {})
        self.data.setdefault("exploration_status", {}); self.data.setdefault("provenance", {}); self.data.setdefault("import_manifest", {})
        self.data.setdefault("conflicts", {})
        self.data.setdefault("ui_state_graph", {}); self.data.setdefault("control_action_graph", {})
        self.data.setdefault("window_dialog_graph", {}); self.data.setdefault("functional_operation_graph", {})

    def save(self) -> None:
        self.root.mkdir(parents=True, exist_ok=True)
        for filename in self.FILES:
            key = filename[:-5]
            (self.root / filename).write_text(json.dumps(self.data[key], ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")

    def _provenance(self, *, kind: str, artifact: Path, confidence: float = 0.6, data: dict[str, Any] | None = None) -> str:
        key = _id("prov", kind, artifact.resolve())
        self.data["provenance"].setdefault(key, {
            "id": key, "kind": kind, "artifact": str(artifact), "confidence": confidence,
            "first_seen": datetime.now(timezone.utc).isoformat(), "data": data or {},
        })
        return key

    def merge_state(self, raw: dict[str, Any], *, artifact: Path, provenance: str = "observed_mapping") -> str:
        semantic = raw.get("semantic_state_fingerprint") or raw.get("fingerprint") or raw.get("state_fingerprint") or ""
        mdi = raw.get("active_mdi") or raw.get("mdi_title") or ""
        window_class = raw.get("window_class") or raw.get("class_name") or ""
        window_title = raw.get("window_title") or raw.get("title") or ""
        controls = raw.get("controls") or raw.get("visible_control_signatures") or []
        state_id = _id("state", semantic, mdi, window_class)
        now = datetime.now(timezone.utc).isoformat()
        record = self.data["states"].setdefault(state_id, {
            "canonical_state_id": state_id, "raw_fingerprints": [], "semantic_fingerprints": [], "active_mdi": mdi or None,
            "window_class": window_class, "dialogs": [], "visible_control_signatures": [], "first_seen": now, "last_seen": now,
            "observation_count": 0, "provenances": [], "confidence": 0.0,
        })
        if window_title:
            record["window_title"] = window_title
        raw_fp = raw.get("fingerprint") or raw.get("state_fingerprint")
        if raw_fp and raw_fp not in record["raw_fingerprints"]: record["raw_fingerprints"].append(raw_fp)
        if semantic and semantic not in record["semantic_fingerprints"]: record["semantic_fingerprints"].append(semantic)
        signatures = [{"control_type": item.get("control_type"), "caption": item.get("caption"), "parent_identity": item.get("parent_identity"), "ordinal": item.get("ordinal"), "enabled": item.get("enabled")} for item in controls if isinstance(item, dict)]
        if signatures: record["visible_control_signatures"] = signatures
        prov = self._provenance(kind=provenance, artifact=artifact)
        if prov not in record["provenances"]: record["provenances"].append(prov)
        record["last_seen"] = now; record["observation_count"] += 1; record["confidence"] = min(1.0, 0.4 + 0.1 * len(record["provenances"]))
        self.data["exploration_status"].setdefault(state_id, {"status": STATUS_PARTIAL, "reason": "state imported; action coverage incomplete"})
        self.data["ui_state_graph"].setdefault(state_id, {"state": state_id, "semantic_fingerprints": record["semantic_fingerprints"], "window_class": window_class, "window_title": window_title})
        return state_id

    def merge_transition(self, raw: dict[str, Any], *, artifact: Path, source_id: str, target_id: str | None, provenance: str = "observed_mapping") -> str:
        action = {
            "action_kind": raw.get("action_kind") or raw.get("control_type") or "activate_control",
            "identity": raw.get("action_identity") or raw.get("control_identity"),
            "caption": raw.get("caption"), "control_type": raw.get("control_type"),
            "parent_identity": raw.get("parent_identity"), "ordinal": raw.get("ordinal"),
        }
        key = _id("edge", source_id, json.dumps(action, sort_keys=True), target_id or "")
        now = datetime.now(timezone.utc).isoformat()
        record = self.data["transitions"].setdefault(key, {
            "id": key, "source_state": source_id, "target_state": target_id, "action": action,
            "effect": raw.get("effect") or ("state_changed" if raw.get("state_changed") else "semantic_noop"),
            "observation_count": 0, "success_count": 0, "failure_count": 0, "first_seen": now, "last_seen": now,
            "provenances": [], "confidence": 0.0, "exploration_status": STATUS_PARTIAL,
        })
        for other_id, other in self.data["transitions"].items():
            if other_id == key:
                continue
            if other.get("source_state") == source_id and other.get("action") == action and other.get("target_state") != target_id:
                conflict_id = _id("conflict", source_id, json.dumps(action, sort_keys=True))
                self.data["conflicts"][conflict_id] = {"id": conflict_id, "source_state": source_id, "action": action, "targets": sorted({str(other.get("target_state")), str(target_id)}), "status": "conflicting_observations"}
        success = bool(raw.get("success", True)) and target_id is not None
        record["observation_count"] += 1; record["success_count" if success else "failure_count"] += 1; record["last_seen"] = now
        prov = self._provenance(kind=provenance, artifact=artifact)
        if prov not in record["provenances"]: record["provenances"].append(prov)
        if raw.get("status") == "stale": record["exploration_status"] = STATUS_STALE
        elif success: record["exploration_status"] = STATUS_KNOWN
        record["confidence"] = min(1.0, 0.4 + 0.1 * record["observation_count"])
        # Parallel projections preserve the distinction between a UI state,
        # a reusable physical control, a window transition and an operation.
        self.data["ui_state_graph"][key] = {"edge": key, "from": source_id, "to": target_id, "action": action}
        control_key = _id("control", action.get("control_type"), action.get("caption"), action.get("parent_identity"), action.get("ordinal"))
        self.data["control_action_graph"].setdefault(control_key, {"id": control_key, "action": action, "uses": []})["uses"].append(key)
        source = self.data["states"].get(source_id, {}); target = self.data["states"].get(target_id or "", {})
        window_key = _id("window", source.get("window_class"), source.get("window_title"), target.get("window_class"), target.get("window_title"))
        self.data["window_dialog_graph"][window_key] = {"id": window_key, "from": {"class": source.get("window_class"), "title": source.get("window_title")}, "to": {"class": target.get("window_class"), "title": target.get("window_title")}, "transition": key}
        operation = raw.get("operation") or "navigation"
        operation_key = _id("operation", operation, action.get("control_type"), action.get("caption"))
        operation_record = self.data["functional_operation_graph"].setdefault(operation_key, {"id": operation_key, "operation": operation, "transition_ids": [], "successes": 0, "failures": 0})
        if key not in operation_record["transition_ids"]: operation_record["transition_ids"].append(key)
        operation_record["successes" if success else "failures"] += 1
        return key

    def useful_frontier(self) -> list[dict[str, Any]]:
        """Known/stale edges remain replay hints; only unknown work is frontier."""
        result = []
        for state_id, state in self.data["states"].items():
            status = self.data["exploration_status"].get(state_id, {}).get("status", STATUS_UNEXPLORED)
            if status in {STATUS_UNEXPLORED, STATUS_PARTIAL}:
                result.append({"state": state_id, "status": status, "active_mdi": state.get("active_mdi")})
        return result

    def known_action(self, *, semantic_fingerprint: str, window_class: str, control: Any) -> bool:
        """Return true only for a previously successful canonical UI edge."""
        candidates = [
            state_id for state_id, state in self.data["states"].items()
            if semantic_fingerprint in state.get("semantic_fingerprints", [])
            and (not window_class or state_id and state.get("window_class", window_class) == window_class)
        ]
        signature = {
            "identity": getattr(control, "identity", None), "caption": getattr(control, "caption", None),
            "control_type": getattr(control, "control_type", None), "parent_identity": getattr(control, "parent_identity", None),
            "ordinal": getattr(control, "ordinal", None),
        }
        for edge in self.data["transitions"].values():
            if edge.get("source_state") not in candidates or edge.get("exploration_status") != STATUS_KNOWN:
                continue
            action = edge.get("action", {})
            if all(action.get(key) == value for key, value in signature.items() if value is not None):
                return True
        return False


class LegacyMappingImporter:
    def __init__(self, *, project_root: Path, store: GlobalMappingStore) -> None:
        self.project_root = project_root; self.store = store

    def _digest(self, path: Path) -> str:
        return hashlib.sha1(path.read_bytes()).hexdigest()

    def import_existing(self, *, dry_run: bool = False) -> dict[str, int]:
        counters = {"legacy_artifacts_found": 0, "states_imported": 0, "states_deduplicated": 0, "transitions_imported": 0, "transitions_deduplicated": 0, "demonstrations_imported": 0, "navigation_edges_imported": 0, "conflicts": 0}
        paths = sorted((self.project_root / "data" / "runtime_maps").rglob("states.json")) + sorted((self.project_root / "data" / "runtime_maps").rglob("transitions.json"))
        paths += [self.project_root / "data" / "knowledge" / "navigation_knowledge.json"]
        paths += sorted((self.project_root / "data" / "capabilities").glob("*.json"))
        paths += [self.project_root / "data" / "knowledge" / "knowledge_store.json"]
        paths += sorted((self.project_root / "data" / "knowledge" / "demonstrations").glob("*.json"))
        seen_states: dict[str, str] = {}
        for path in paths:
            if not path.is_file(): continue
            counters["legacy_artifacts_found"] += 1
            digest = self._digest(path)
            if self.store.data["import_manifest"].get(str(path)) == digest: continue
            raw = _read(path, {})
            if path.name == "states.json":
                for state in raw if isinstance(raw, list) else raw.get("states", []):
                    before = len(self.store.data["states"]); state_id = self.store.merge_state(state, artifact=path)
                    if len(self.store.data["states"]) > before: counters["states_imported"] += 1
                    else: counters["states_deduplicated"] += 1
                    for fingerprint in self.store.data["states"][state_id].get("raw_fingerprints", []): seen_states[fingerprint] = state_id
            elif path.name == "transitions.json":
                for edge in raw if isinstance(raw, list) else raw.get("transitions", []):
                    source = seen_states.get(edge.get("from_state")) or self.store.merge_state({"fingerprint": edge.get("from_state"), "semantic_state_fingerprint": edge.get("from_semantic_state") or edge.get("from_state")}, artifact=path)
                    target = None
                    if edge.get("to_state"):
                        target = seen_states.get(edge.get("to_state")) or self.store.merge_state({"fingerprint": edge.get("to_state"), "semantic_state_fingerprint": edge.get("to_semantic_state") or edge.get("to_state")}, artifact=path)
                    before = len(self.store.data["transitions"]); self.store.merge_transition(edge, artifact=path, source_id=source, target_id=target)
                    if len(self.store.data["transitions"]) > before: counters["transitions_imported"] += 1
                    else: counters["transitions_deduplicated"] += 1
            elif path.name == "navigation_knowledge.json":
                for state in raw.get("states", {}).values():
                    self.store.merge_state({"fingerprint": state.get("fingerprint"), "mdi_title": state.get("mdi_title"), "window_class": state.get("window_class"), "controls": state.get("controls_summary", [])}, artifact=path, provenance="legacy_capability_registry")
                for edge in raw.get("transitions", {}).values():
                    source_raw = raw.get("states", {}).get(edge.get("from_state_id"), {})
                    target_raw = raw.get("states", {}).get(edge.get("to_state_id"), {})
                    source = self.store.merge_state({"fingerprint": source_raw.get("fingerprint"), "window_class": source_raw.get("window_class")}, artifact=path, provenance="legacy_capability_registry")
                    target = self.store.merge_state({"fingerprint": target_raw.get("fingerprint"), "window_class": target_raw.get("window_class")}, artifact=path, provenance="legacy_capability_registry")
                    self.store.merge_transition({"action_kind": edge.get("action_kind"), "action_identity": edge.get("action_identity"), "status": edge.get("status"), "success": edge.get("success_count", 0) > 0}, artifact=path, source_id=source, target_id=target, provenance="legacy_capability_registry"); counters["navigation_edges_imported"] += 1
            elif path.parent.name == "capabilities" or path.name == "knowledge_store.json":
                count = len(raw) if isinstance(raw, list) else len(raw.get("concepts", raw.get("capabilities", raw))) if isinstance(raw, dict) else 0
                self.store._provenance(kind="legacy_capability_registry", artifact=path, confidence=0.7, data={"records": count})
            else:  # human demonstration
                self.store._provenance(kind="human_demonstration", artifact=path, confidence=0.5, data={"target": raw.get("target"), "steps": len(raw.get("steps", []))})
                counters["demonstrations_imported"] += 1
            self.store.data["import_manifest"][str(path)] = digest
        if not dry_run: self.store.save()
        counters["conflicts"] = len(self.store.data["conflicts"])
        return counters
