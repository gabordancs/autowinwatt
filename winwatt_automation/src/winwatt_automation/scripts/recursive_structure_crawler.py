"""Recursive, unattended, sandbox-only crawler for the global Szerkezetek UI.

The crawler explores the UI as a graph.  A frontier owns one disposable
sandbox/session: its parent path is replayed once, then all safe sibling
controls are attempted from that parent state.  After each attempt the crawler
must prove that it restored the parent state; a failed local reset falls back
to reopening the *same* sandbox and replaying only that parent path.  This
keeps the old safety properties without paying a copy/launch cost per sibling.

Normal traversal never invokes controls classified as blocked or commit
candidates by SandboxUIExplorer.  Creation commits remain a separate explicit
opt-in experiment handled by StructureCatalogDeepMapper.
"""
from __future__ import annotations

import argparse
import json
import time
from collections import deque
from dataclasses import dataclass, asdict
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any

from winwatt_automation.knowledge.models import EvidenceRef
from winwatt_automation.knowledge.global_mapping import GlobalMappingStore
from winwatt_automation.live_ui.app_connector import get_main_window
from winwatt_automation.navigation.store import NavigationKnowledgeStore
from winwatt_automation.research.ui_exploration import SandboxUIExplorer, WindowSummary
from winwatt_automation.research.demonstrations import DemonstrationGuide, DemonstrationStore
from winwatt_automation.runtime_mapping.mdi_state_model import (
    activate_structures_catalog_native,
    active_mdi_title,
)
from winwatt_automation.runtime_mapping.state_fingerprints import semantic_state_fingerprint
from winwatt_automation.services.winwatt_service import WinWattService


CRAWL_TYPES = {"Button", "MenuItem", "TabItem", "TreeItem", "ListItem", "ComboBox"}


@dataclass(frozen=True)
class PathStep:
    identity: str
    expected_from_state: str | None = None
    expected_to_state: str | None = None


@dataclass
class FrontierNode:
    path: list[PathStep]
    depth: int
    guidance_priority: int = 0


def parse_stop_at(value: str) -> datetime:
    try:
        hour, minute = (int(part) for part in value.split(":", 1))
    except Exception as exc:
        raise argparse.ArgumentTypeError("--stop-at must be HH:MM") from exc
    if not (0 <= hour <= 23 and 0 <= minute <= 59):
        raise argparse.ArgumentTypeError("--stop-at must be HH:MM")
    now = datetime.now()
    target = now.replace(hour=hour, minute=minute, second=0, microsecond=0)
    if target <= now:
        target += timedelta(days=1)
    return target


def write_json(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2, default=str) + "\n", encoding="utf-8")


def control_record(item: Any) -> dict[str, Any]:
    return {
        "identity": item.identity,
        "caption": item.caption or None,
        "caption_source": item.caption_source,
        "control_type": item.control_type,
        "class_name": item.class_name,
        "enabled": item.enabled,
        "parent_identity": item.parent_identity,
        "ordinal": item.ordinal,
    }


def state_record(state: WindowSummary) -> dict[str, Any]:
    return {
        "fingerprint": state.state_fingerprint,
        "semantic_state_fingerprint": semantic_state_fingerprint(state),
        "window_identity": state.identity,
        "window_title": state.title,
        "window_class": state.class_name,
        "controls": [control_record(item) for item in state.controls],
        "captured_at": datetime.now().isoformat(),
    }


class RecursiveStructureCrawler:
    def __init__(
        self,
        *,
        source_project: Path,
        output_root: Path,
        stop_at: datetime,
        max_depth: int = 12,
        max_actions: int = 5000,
        max_states: int = 2000,
        replay_pause_seconds: float = 0.08,
        import_navigation: bool = True,
        resume: bool = False,
        guide: str | None = None,
        demonstrations_dir: Path | None = None,
        global_store_dir: Path | None = None,
        background_mode: bool = False,
        aggressive_sandbox: bool = False,
    ) -> None:
        self.source_project = source_project.resolve()
        self.output_root = output_root.resolve()
        self.stop_at = stop_at
        self.max_depth = max_depth
        self.max_actions = max_actions
        self.max_states = max_states
        self.replay_pause_seconds = replay_pause_seconds
        self.import_navigation = import_navigation
        self.resume = resume
        self.guide_name = guide
        self.demonstrations_dir = demonstrations_dir or Path(__file__).resolve().parents[3] / "data" / "knowledge" / "demonstrations"
        self.guide = DemonstrationGuide(DemonstrationStore(self.demonstrations_dir).load(guide)) if guide else None
        self.global_mapping = GlobalMappingStore(global_store_dir) if global_store_dir else None
        self.background_mode = background_mode
        self.aggressive_sandbox = aggressive_sandbox

        self.states: dict[str, dict[str, Any]] = {}
        self.transitions: list[dict[str, Any]] = []
        self.errors: list[dict[str, Any]] = []
        self.visited_actions: set[tuple[str, str, str]] = set()
        self.visited_paths: set[tuple[str, ...]] = set()
        self.actions_attempted = 0
        self.replays = 0
        self.replay_failures = 0
        self.repeats_avoided = 0
        self.max_depth_reached = 0
        self.reset_events: list[dict[str, Any]] = []
        self.guided_frontier_decisions: list[dict[str, Any]] = []
        # Kept separately so a wrapper can make Ctrl+C durable without losing
        # the work queue that has not yet been visited.
        self._active_frontier: deque[FrontierNode] = deque()
        self.counters: dict[str, int] = {
            "winwatt_launches": 0,
            "project_reopens": 0,
            "sandbox_copies": 0,
            "parent_path_replays": 0,
            "local_resets": 0,
            "frontiers_processed": 0,
            "children_discovered": 0,
            "actions_attempted": 0,
            "actions_skipped_duplicate": 0,
            "actions_blocked_safety": 0,
            "reset_failures": 0,
            "replay_failures": 0,
            "errors": 0,
            "semantic_reset_successes": 0,
            "popup_resets": 0,
            "dialog_resets": 0,
            "selection_resets": 0,
            "mdi_resets": 0,
            "project_reopen_fallbacks": 0,
            "winwatt_relaunch_fallbacks": 0,
            "fingerprint_only_mismatches": 0,
            "failed_actions_no_reset": 0,
            "actions_skipped_global_known": 0,
            "branch_recoveries": 0,
            "sandbox_mutations": 0,
            "sandboxes_discarded": 0,
        }

    def _deadline(self) -> bool:
        return datetime.now() >= self.stop_at

    def _checkpoint(self, frontier: deque[FrontierNode], *, status: str = "running") -> None:
        payload = {
            "status": status,
            "source_project": str(self.source_project),
            "stop_at": self.stop_at.isoformat(),
            "states": len(self.states),
            "transitions": len(self.transitions),
            "actions_attempted": self.actions_attempted,
            "visited_action_pairs": len(self.visited_actions),
            "frontier_size": len(frontier),
            "max_depth_reached": self.max_depth_reached,
            "replays": self.replays,
            "replay_failures": self.replay_failures,
            "repeats_avoided": self.repeats_avoided,
            "errors": self.errors,
            "performance_counters": self.counters,
            "guide": self.guide_name,
            "updated_at": datetime.now().isoformat(),
        }
        write_json(self.output_root / "recursive_summary.json", payload)
        write_json(self.output_root / "states.json", list(self.states.values()))
        write_json(self.output_root / "transitions.json", self.transitions)
        write_json(self.output_root / "reset_events.json", self.reset_events)
        write_json(
            self.output_root / "frontier.json",
            [{"depth": node.depth, "path": [asdict(step) for step in node.path], "guidance_priority": node.guidance_priority} for node in frontier],
        )
        write_json(self.output_root / "guided_frontier_decisions.json", self.guided_frontier_decisions)
        if self.global_mapping:
            self.global_mapping.save()
        write_json(
            self.output_root / "visited_actions.json",
            [
                {"state_fingerprint": state, "control_identity": identity, "relevant_context": context}
                for state, identity, context in sorted(self.visited_actions)
            ],
        )
        write_json(self.output_root / "visited_paths.json", [list(path) for path in sorted(self.visited_paths)])

    def checkpoint_interrupted(self) -> None:
        """Persist the currently queued work when a long unattended run is interrupted."""
        self._checkpoint(self._active_frontier, status="interrupted")

    def _fresh_explorer(self, branch_id: str) -> tuple[WinWattService, SandboxUIExplorer, Path]:
        branch_dir = self.output_root / "sandboxes" / branch_id
        sandbox = branch_dir / "sandbox" / self.source_project.name
        service = WinWattService()
        service.create_sandbox(self.source_project, sandbox)
        self.counters["sandbox_copies"] += 1
        service.open_project(sandbox)
        self.counters["winwatt_launches"] += 1
        if not activate_structures_catalog_native() or active_mdi_title() != "Szerkezetek":
            raise RuntimeError("verified catalog.structure.open did not reach Szerkezetek")
        return service, SandboxUIExplorer(get_main_window(), sandbox, aggressive_sandbox=self.aggressive_sandbox), sandbox

    def _reopen_same_sandbox(self, service: WinWattService, sandbox: Path) -> SandboxUIExplorer:
        """Recover a parent state without making another source-project copy.

        First use the verified Open Project dialog in the live, owned process.
        The historical launcher is retained only as a fail-closed fallback.
        """
        self.counters["project_reopens"] += 1
        self.counters["project_reopen_fallbacks"] += 1
        in_process = service.reopen_sandbox_project_in_current_session(sandbox)
        if not bool(in_process.get("success")):
            service.open_project(sandbox)
            self.counters["winwatt_launches"] += 1
            self.counters["winwatt_relaunch_fallbacks"] += 1
        if not activate_structures_catalog_native() or active_mdi_title() != "Szerkezetek":
            raise RuntimeError("verified catalog.structure.open did not reach Szerkezetek after reset")
        self.counters["sandboxes_discarded"] += 1
        return SandboxUIExplorer(get_main_window(), sandbox, aggressive_sandbox=self.aggressive_sandbox)

    def _replay_path(self, explorer: SandboxUIExplorer, path: list[PathStep]) -> WindowSummary:
        state = explorer.inspect_window()
        for index, step in enumerate(path, start=1):
            self.replays += 1
            self.counters["parent_path_replays"] += 1
            if step.expected_from_state and state.state_fingerprint != step.expected_from_state:
                raise RuntimeError(
                    f"replay source mismatch at step {index}: expected {step.expected_from_state}, got {state.state_fingerprint}"
                )
            action = explorer.activate_control(step.identity, index)
            if not action.success or action.state_after is None:
                raise RuntimeError(f"replay failed at step {index}: {action.failure}")
            state = action.state_after
            if step.expected_to_state and state.state_fingerprint != step.expected_to_state:
                raise RuntimeError(
                    f"replay target mismatch at step {index}: expected {step.expected_to_state}, got {state.state_fingerprint}"
                )
            if self.replay_pause_seconds:
                time.sleep(self.replay_pause_seconds)
        return state

    @staticmethod
    def _context_key(control: Any) -> str:
        """Identity alone is not sufficient for owner-drawn repeated controls."""
        return f"{control.control_type}|{control.parent_identity or ''}|{control.ordinal if control.ordinal is not None else ''}"

    def _match_parent(self, expected: WindowSummary, observed: WindowSummary) -> tuple[bool, str]:
        if observed.state_fingerprint == expected.state_fingerprint:
            return True, "raw_fingerprint"
        if semantic_state_fingerprint(observed) == semantic_state_fingerprint(expected):
            self.counters["fingerprint_only_mismatches"] += 1
            return True, "semantic_fingerprint"
        return False, "semantic_mismatch"

    def _record_reset(
        self,
        *,
        control: Any | None,
        expected: WindowSummary,
        observed: WindowSummary | None,
        strategy: str,
        result: str,
        detail: str | None = None,
    ) -> None:
        self.reset_events.append({
            "at": datetime.now().isoformat(),
            "strategy": strategy,
            "result": result,
            "action_identity": getattr(control, "identity", None),
            "action_caption": getattr(control, "caption", None),
            "action_control_type": getattr(control, "control_type", None),
            "expected_raw_fingerprint": expected.state_fingerprint,
            "expected_semantic_fingerprint": semantic_state_fingerprint(expected),
            "observed_raw_fingerprint": observed.state_fingerprint if observed else None,
            "observed_semantic_fingerprint": semantic_state_fingerprint(observed) if observed else None,
            "detail": detail,
        })

    def _restore_parent(
        self,
        *,
        service: WinWattService,
        explorer: SandboxUIExplorer,
        sandbox: Path,
        path: list[PathStep],
        expected_parent: WindowSummary,
        control: Any | None = None,
        action: Any | None = None,
    ) -> tuple[SandboxUIExplorer, WindowSummary]:
        """Return a proven copy of ``expected_parent`` or raise.

        Escape is only a local optimization: its outcome is accepted solely if
        the resulting fingerprint equals the parent fingerprint.  Otherwise
        the crawler reopens the current disposable project and replays the
        already-known parent path.
        """
        # A no-op has already remained at the parent.  Do not inject Esc into
        # an otherwise stable Delphi editor merely to "reset" it.
        if action is not None and action.state_after is not None:
            same, kind = self._match_parent(expected_parent, action.state_after)
            if same:
                self.counters["local_resets"] += 1
                self.counters["semantic_reset_successes"] += 1
                self._record_reset(control=control, expected=expected_parent, observed=action.state_after, strategy="no_op", result=kind)
                return explorer, action.state_after
        # A blocked/commit candidate is intentionally not clicked by
        # SandboxUIExplorer.  Its state_after is None, but its pre-action
        # snapshot was the parent: pressing Escape here used to manufacture a
        # needless state change and then a project relaunch.
        if action is not None and not action.success:
            observed = explorer.inspect_window()
            same, kind = self._match_parent(expected_parent, observed)
            if same:
                self.counters["local_resets"] += 1
                self.counters["semantic_reset_successes"] += 1
                self.counters["failed_actions_no_reset"] += 1
                self._record_reset(control=control, expected=expected_parent, observed=observed, strategy="failed_action_no_reset", result=kind)
                return explorer, observed
        try:
            reset = explorer.go_back(self.actions_attempted)
            after_reset = reset.state_after
            if reset.success and after_reset:
                same, kind = self._match_parent(expected_parent, after_reset)
            else:
                same, kind = False, "go_back_failed"
            if same:
                self.counters["local_resets"] += 1
                self.counters["semantic_reset_successes"] += 1
                if control is not None and control.control_type == "MenuItem":
                    self.counters["popup_resets"] += 1
                elif control is not None and control.control_type in {"TreeItem", "ListItem", "ComboBox", "TabItem"}:
                    self.counters["selection_resets"] += 1
                elif action is not None and action.state_after and action.state_after.class_name != expected_parent.class_name:
                    self.counters["dialog_resets"] += 1
                self._record_reset(control=control, expected=expected_parent, observed=after_reset, strategy="go_back", result=kind)
                return explorer, after_reset
        except Exception as exc:
            kind = "go_back_exception"
            go_back_detail = repr(exc)
        else:
            go_back_detail = None

        # MDI actions (notably minimize/maximize/close) are locally restored
        # by the already-verified catalog opener before escalating to a costly
        # project reopen.  This has no write side-effect.
        try:
            if activate_structures_catalog_native() and active_mdi_title() == "Szerkezetek":
                mdi_explorer = SandboxUIExplorer(get_main_window(), sandbox, aggressive_sandbox=self.aggressive_sandbox)
                mdi_state = mdi_explorer.inspect_window()
                same, mdi_kind = self._match_parent(expected_parent, mdi_state)
                if same:
                    self.counters["local_resets"] += 1
                    self.counters["semantic_reset_successes"] += 1
                    self.counters["mdi_resets"] += 1
                    self._record_reset(control=control, expected=expected_parent, observed=mdi_state, strategy="mdi_catalog_restore", result=mdi_kind)
                    return mdi_explorer, mdi_state
                kind = f"mdi_{mdi_kind}"
        except Exception as exc:
            kind = "mdi_restore_exception"
            mdi_detail = repr(exc)
        else:
            mdi_detail = None
        self.counters["reset_failures"] += 1
        self._record_reset(control=control, expected=expected_parent, observed=None, strategy="project_reopen", result=kind, detail=mdi_detail or go_back_detail)
        reopened = self._reopen_same_sandbox(service, sandbox)
        restored = self._replay_path(reopened, path)
        same, reopen_kind = self._match_parent(expected_parent, restored)
        if not same:
            raise RuntimeError(
                f"reset replay mismatch: expected {expected_parent.state_fingerprint}, got {restored.state_fingerprint}"
            )
        self._record_reset(control=control, expected=expected_parent, observed=restored, strategy="project_reopen", result=reopen_kind)
        return reopened, restored

    def _load_resume(self) -> deque[FrontierNode] | None:
        if not self.resume or not (self.output_root / "frontier.json").is_file():
            return None
        def read(name: str, fallback: Any) -> Any:
            path = self.output_root / name
            return json.loads(path.read_text(encoding="utf-8")) if path.is_file() else fallback
        self.states = {item["fingerprint"]: item for item in read("states.json", []) if item.get("fingerprint")}
        self.transitions = list(read("transitions.json", []))
        self.errors = list(read("recursive_summary.json", {}).get("errors", []))
        summary = read("recursive_summary.json", {})
        self.counters.update({key: int(value) for key, value in summary.get("performance_counters", {}).items() if key in self.counters})
        self.actions_attempted = int(summary.get("actions_attempted", self.counters["actions_attempted"]))
        self.replays = int(summary.get("replays", 0)); self.replay_failures = int(summary.get("replay_failures", 0))
        self.repeats_avoided = int(summary.get("repeats_avoided", 0)); self.max_depth_reached = int(summary.get("max_depth_reached", 0))
        self.visited_actions = {
            (str(item["state_fingerprint"]), str(item["control_identity"]), str(item.get("relevant_context", "")))
            for item in read("visited_actions.json", [])
        }
        frontier = deque(
            FrontierNode(path=[PathStep(**step) for step in item.get("path", [])], depth=int(item["depth"]), guidance_priority=int(item.get("guidance_priority", 0)))
            for item in read("frontier.json", [])
        )
        self.visited_paths = {tuple(str(value) for value in path) for path in read("visited_paths.json", [])}
        return frontier

    @staticmethod
    def _sort_frontier(frontier: deque[FrontierNode]) -> deque[FrontierNode]:
        # BFS depth remains primary; human evidence only breaks ties inside a
        # depth, preserving alternative-path discovery.
        return deque(sorted(frontier, key=lambda item: (item.depth, -item.guidance_priority)))

    def _background_score(self, state: WindowSummary, control: Any, *, child_state: WindowSummary | None = None, depth: int = 0) -> int:
        """Novelty/depth ranking only; safety is evaluated separately."""
        caption = (control.caption or "").casefold()
        score = depth * 1_000
        if control.control_type in {"MenuItem", "TreeItem", "TabItem", "ComboBox"}: score += 180
        if control.control_type == "Button": score += 40
        if not control.caption: score += 130  # observed owner-drawn branch, not safety admission
        if self.aggressive_sandbox and self._operation_kind(control) != "navigation": score += 650
        if any(term in caption for term in ("görget", "scroll", "csúszka", "kis méret", "teljes méret", "fókusz")): score -= 800
        if child_state and child_state.class_name != state.class_name: score += 350
        if child_state and child_state.state_fingerprint != state.state_fingerprint: score += 100
        return score

    @staticmethod
    def _operation_kind(control: Any) -> str:
        text = (getattr(control, "caption", "") or "").casefold()
        for kind, terms in {
            "delete": ("töröl", "torol", "delete", "remove"),
            "create": ("létrehoz", "letrehoz", "új", "uj", "felvesz", "add"),
            "copy": ("másol", "masol", "copy", "duplicate"),
            "rename": ("átnevez", "atnevez", "rename"),
            "edit": ("módosít", "modosit", "edit"),
            "save": ("ment", "save", "apply", "ok"),
            "assign": ("hozzáad", "hozzaad", "assign"),
        }.items():
            if any(term in text for term in terms):
                return kind
        return "navigation"

    def _prioritize_controls(self, state: WindowSummary, controls: list[Any]) -> list[Any]:
        base = list(controls)
        if self.background_mode:
            base = sorted(base, key=lambda item: -self._background_score(state, item, depth=0))
        if not self.guide:
            return base
        try:
            decisions = self.guide.decisions(state, active_mdi_title(), base)
        except Exception as exc:
            self.errors.append({"stage": "guidance", "state": state.state_fingerprint, "error": repr(exc)})
            return base
        by_id = {item["control_identity"]: item for item in decisions}
        self.guided_frontier_decisions.append({
            "at": datetime.now().isoformat(), "state_fingerprint": state.state_fingerprint,
            "semantic_state_fingerprint": semantic_state_fingerprint(state), "decisions": decisions,
            "target_candidate_reached": self.guide.target_candidate(state, active_mdi_title()),
        })
        return sorted(base, key=lambda control: -int(by_id[control.identity]["final_priority"]))

    def _remember_state(self, state: WindowSummary) -> None:
        record = self.states.setdefault(state.state_fingerprint, state_record(state))
        if self.guide:
            try:
                record["target_candidate_reached"] = self.guide.target_candidate(state, active_mdi_title())
            except Exception:
                record["target_candidate_reached"] = False

    def _record_transition(
        self,
        *,
        before: WindowSummary,
        control: Any,
        action: Any,
        depth: int,
        path: list[PathStep],
    ) -> None:
        after = action.state_after
        self.transitions.append(
            {
                "from_state": before.state_fingerprint,
                "from_semantic_state": semantic_state_fingerprint(before),
                "to_state": after.state_fingerprint if after else None,
                "to_semantic_state": semantic_state_fingerprint(after) if after else None,
                "action_identity": control.identity,
                "caption": control.caption or None,
                "caption_source": control.caption_source,
                "control_type": control.control_type,
                "parent_identity": control.parent_identity,
                "ordinal": control.ordinal,
                "safety_class": action.safety_class,
                "success": action.success,
                "failure": action.failure,
                "state_changed": bool(after and before.state_fingerprint != after.state_fingerprint),
                "depth": depth,
                "path": [asdict(step) for step in path],
                "controls_added": action.controls_added,
                "controls_removed": action.controls_removed,
                "operation": self._operation_kind(control),
                "observed_at": datetime.now().isoformat(),
            }
        )
        if self.global_mapping:
            source = self.global_mapping.merge_state(state_record(before), artifact=self.output_root / "transitions.json")
            target = self.global_mapping.merge_state(state_record(after), artifact=self.output_root / "transitions.json") if after else None
            self.global_mapping.merge_transition(self.transitions[-1], artifact=self.output_root / "transitions.json", source_id=source, target_id=target)

    def _import_transition(self, before: WindowSummary, control: Any, action: Any) -> None:
        if not self.import_navigation or not action.success or action.state_after is None:
            return
        store = NavigationKnowledgeStore()
        source = store.upsert_state(
            before.state_fingerprint,
            before.class_name,
            before.title,
            [],
            "recursive_structure_crawler",
            semantic_context="catalog.structure",
        )
        target = store.upsert_state(
            action.state_after.state_fingerprint,
            action.state_after.class_name,
            action.state_after.title,
            [],
            "recursive_structure_crawler",
            semantic_context="catalog.structure",
        )
        store.upsert_transition(
            source.id,
            "activate_control",
            target.id,
            action_identity=control.identity,
            semantic_action="structure catalog recursive mapped navigation",
            expected_state=action.state_after.state_fingerprint,
            status="observed",
            evidence=EvidenceRef(
                kind="recursive_structure_mapping",
                description="Deterministic sandbox recursive UI observation",
                deterministic=False,
                data={
                    "control_type": control.control_type,
                    "caption": control.caption or None,
                    "safety_class": action.safety_class,
                },
            ),
        )

    def run(self) -> dict[str, Any]:
        self.output_root.mkdir(parents=True, exist_ok=True)
        restored_frontier = self._load_resume()
        frontier = restored_frontier if restored_frontier is not None else deque([FrontierNode(path=[], depth=0)])
        self._active_frontier = frontier
        self._checkpoint(frontier)

        branch_counter = 0
        while frontier:
            if self._deadline() or self.actions_attempted >= self.max_actions or len(self.states) >= self.max_states:
                break

            node = frontier.popleft()
            path_key = tuple(step.identity for step in node.path)
            if path_key in self.visited_paths:
                self.repeats_avoided += 1
                continue
            self.visited_paths.add(path_key)
            self.counters["frontiers_processed"] += 1
            self.max_depth_reached = max(self.max_depth_reached, node.depth)

            branch_counter += 1
            branch_id = f"branch_{branch_counter:06d}_d{node.depth:02d}"
            try:
                service, explorer, _sandbox = self._fresh_explorer(branch_id)
                state = self._replay_path(explorer, node.path)
            except Exception as exc:
                self.replay_failures += 1
                self.counters["replay_failures"] += 1
                self.counters["branch_recoveries"] += 1
                self.errors.append(
                    {"stage": "replay", "branch": branch_id, "depth": node.depth, "error": repr(exc)}
                )
                self._checkpoint(frontier)
                continue

            self._remember_state(state)
            if node.depth >= self.max_depth:
                self._checkpoint(frontier)
                continue

            controls = [
                item
                for item in state.controls
                if item.control_type in (CRAWL_TYPES | ({"Edit"} if self.aggressive_sandbox else set())) and item.enabled
            ]
            controls = self._prioritize_controls(state, controls)

            interrupted = False
            for control in controls:
                if self._deadline() or self.actions_attempted >= self.max_actions or len(self.states) >= self.max_states:
                    interrupted = True
                    break

                pair = (state.state_fingerprint, control.identity, self._context_key(control))
                if pair in self.visited_actions:
                    self.repeats_avoided += 1
                    self.counters["actions_skipped_duplicate"] += 1
                    continue
                if self.global_mapping and self.global_mapping.known_action(
                    semantic_fingerprint=semantic_state_fingerprint(state), window_class=state.class_name, control=control,
                ):
                    self.counters["actions_skipped_global_known"] += 1
                    continue
                self.visited_actions.add(pair)
                self.actions_attempted += 1
                self.counters["actions_attempted"] = self.actions_attempted

                sibling_id = f"action_{self.actions_attempted:07d}_d{node.depth:02d}"
                try:
                    before = state
                    live_control = next(
                        (item for item in before.controls if item.identity == control.identity),
                        None,
                    )
                    if live_control is None:
                        raise RuntimeError("frontier control disappeared from restored parent state")
                    if self.aggressive_sandbox and live_control.control_type == "Edit":
                        action = explorer.set_control_value(
                            live_control.identity, f"AI_TEST_MAP_{self.actions_attempted:07d}", self.actions_attempted,
                        )
                    else:
                        action = explorer.activate_control(live_control.identity, self.actions_attempted)
                    if action.safety_class in {"blocked", "commit_candidate"}:
                        self.counters["actions_blocked_safety"] += 1
                    elif action.safety_class == "sandbox_mutation" and action.success:
                        self.counters["sandbox_mutations"] += 1
                    self._record_transition(
                        before=before,
                        control=live_control,
                        action=action,
                        depth=node.depth,
                        path=node.path,
                    )
                    if action.success and action.state_after is not None:
                        after = action.state_after
                        self._remember_state(after)
                        self._import_transition(before, live_control, action)
                        if after.state_fingerprint != before.state_fingerprint:
                            child_path = node.path + [
                                PathStep(
                                    identity=live_control.identity,
                                    expected_from_state=before.state_fingerprint,
                                    expected_to_state=after.state_fingerprint,
                                )
                            ]
                            child_key = tuple(step.identity for step in child_path)
                            if child_key not in self.visited_paths:
                                guidance_priority = self._background_score(before, live_control, child_state=after, depth=node.depth + 1) if self.background_mode else 0
                                if self.guide:
                                    try:
                                        guidance_priority = max(
                                            (item["guidance_score"] for item in self.guide.decisions(after, active_mdi_title(), after.controls)),
                                            default=0,
                                        )
                                    except Exception:
                                        guidance_priority = 0
                                frontier.append(FrontierNode(path=child_path, depth=node.depth + 1, guidance_priority=guidance_priority))
                                frontier = (deque(sorted(frontier, key=lambda item: (-item.guidance_priority, -item.depth))) if self.background_mode else self._sort_frontier(frontier))
                                self._active_frontier = frontier
                                self.counters["children_discovered"] += 1
                            else:
                                self.repeats_avoided += 1
                    # Do not assume Escape restores a Delphi branch.  The
                    # next sibling always starts from a fingerprint-proven
                    # parent; failure reopens this same sandbox only.
                    explorer, state = self._restore_parent(
                        service=service,
                        explorer=explorer,
                        sandbox=_sandbox,
                        path=node.path,
                        expected_parent=before,
                        control=live_control,
                        action=action,
                    )
                except Exception as exc:
                    self.errors.append(
                        {
                            "stage": "action",
                            "branch": sibling_id,
                            "depth": node.depth,
                            "state": state.state_fingerprint,
                            "control_identity": control.identity,
                            "caption": control.caption or None,
                            "error": repr(exc),
                        }
                    )
                    self.counters["errors"] += 1
                    self.counters["branch_recoveries"] += 1
                self._checkpoint(frontier)

            # A deadline/action ceiling can cut through a sibling set. Keep
            # this parent at the front of the durable queue; its contextual
            # visited-action records prevent replaying already completed
            # siblings when ``--resume`` continues it later.
            if interrupted:
                self.visited_paths.discard(path_key)
                frontier.appendleft(node)
                self._checkpoint(frontier)
                break

        if self._deadline():
            status = "deadline_reached"
        elif self.actions_attempted >= self.max_actions:
            status = "action_budget_reached"
        elif len(self.states) >= self.max_states:
            status = "state_budget_reached"
        elif not frontier:
            status = "frontier_exhausted"
        else:
            status = "stopped"

        self._checkpoint(frontier, status=status)
        result = {
            "status": status,
            "states": len(self.states),
            "transitions": len(self.transitions),
            "actions_attempted": self.actions_attempted,
            "visited_action_pairs": len(self.visited_actions),
            "max_depth_reached": self.max_depth_reached,
            "frontier_remaining": len(frontier),
            "replays": self.replays,
            "replay_failures": self.replay_failures,
            "repeats_avoided": self.repeats_avoided,
            "errors": len(self.errors),
            "performance_counters": self.counters,
            "output_root": str(self.output_root),
            "finished_at": datetime.now().isoformat(),
        }
        write_json(self.output_root / "result.json", result)
        return result


def main() -> int:
    parser = argparse.ArgumentParser(description="Recursive sandbox-only Structure Catalog crawler")
    parser.add_argument("--project", required=True, type=Path)
    parser.add_argument("--output-root", required=True, type=Path)
    parser.add_argument("--stop-at", default="08:00", help="Local deadline HH:MM; default 08:00")
    parser.add_argument("--max-depth", type=int, default=12)
    parser.add_argument("--max-actions", type=int, default=5000)
    parser.add_argument("--max-states", type=int, default=2000)
    parser.add_argument("--replay-pause-seconds", type=float, default=0.08)
    parser.add_argument("--no-import-navigation", action="store_true")
    parser.add_argument("--resume", action="store_true", help="Continue a checkpointed crawl in output-root")
    parser.add_argument("--guide", help="Human demonstration name; guidance only, never safety authority")
    parser.add_argument("--demonstrations-dir", type=Path)
    parser.add_argument("--global-store-dir", type=Path, help="Skip globally known observed edges and merge new observations")
    args = parser.parse_args()

    crawler = RecursiveStructureCrawler(
        source_project=args.project,
        output_root=args.output_root,
        stop_at=parse_stop_at(args.stop_at),
        max_depth=max(args.max_depth, 0),
        max_actions=max(args.max_actions, 1),
        max_states=max(args.max_states, 1),
        replay_pause_seconds=max(args.replay_pause_seconds, 0.0),
        import_navigation=not args.no_import_navigation,
        resume=args.resume,
        guide=args.guide,
        demonstrations_dir=args.demonstrations_dir,
        global_store_dir=args.global_store_dir,
    )
    result = crawler.run()
    print(json.dumps(result, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
