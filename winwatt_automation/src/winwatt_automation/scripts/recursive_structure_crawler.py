"""Recursive, unattended, sandbox-only crawler for the global Szerkezetek UI.

The crawler explores the UI as a graph.  Each frontier path is replayed from a
fresh sandbox/session before the next action is tried, so traversal does not
rely on fragile multi-level Escape backtracking.  Safe observed controls are
explored breadth-first until the wall-clock deadline or budgets are reached.

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
from winwatt_automation.live_ui.app_connector import get_main_window
from winwatt_automation.navigation.store import NavigationKnowledgeStore
from winwatt_automation.research.ui_exploration import SandboxUIExplorer, WindowSummary
from winwatt_automation.runtime_mapping.mdi_state_model import (
    activate_structures_catalog_native,
    active_mdi_title,
)
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
    ) -> None:
        self.source_project = source_project.resolve()
        self.output_root = output_root.resolve()
        self.stop_at = stop_at
        self.max_depth = max_depth
        self.max_actions = max_actions
        self.max_states = max_states
        self.replay_pause_seconds = replay_pause_seconds
        self.import_navigation = import_navigation

        self.states: dict[str, dict[str, Any]] = {}
        self.transitions: list[dict[str, Any]] = []
        self.errors: list[dict[str, Any]] = []
        self.visited_actions: set[tuple[str, str]] = set()
        self.visited_paths: set[tuple[str, ...]] = set()
        self.actions_attempted = 0
        self.replays = 0
        self.replay_failures = 0
        self.repeats_avoided = 0
        self.max_depth_reached = 0

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
            "updated_at": datetime.now().isoformat(),
        }
        write_json(self.output_root / "recursive_summary.json", payload)
        write_json(self.output_root / "states.json", list(self.states.values()))
        write_json(self.output_root / "transitions.json", self.transitions)
        write_json(
            self.output_root / "frontier.json",
            [{"depth": node.depth, "path": [asdict(step) for step in node.path]} for node in frontier],
        )

    def _fresh_explorer(self, branch_id: str) -> tuple[WinWattService, SandboxUIExplorer, Path]:
        branch_dir = self.output_root / "sandboxes" / branch_id
        sandbox = branch_dir / "sandbox" / self.source_project.name
        service = WinWattService()
        service.create_sandbox(self.source_project, sandbox)
        service.open_project(sandbox)
        if not activate_structures_catalog_native() or active_mdi_title() != "Szerkezetek":
            raise RuntimeError("verified catalog.structure.open did not reach Szerkezetek")
        return service, SandboxUIExplorer(get_main_window(), sandbox), sandbox

    def _replay_path(self, explorer: SandboxUIExplorer, path: list[PathStep]) -> WindowSummary:
        state = explorer.inspect_window()
        for index, step in enumerate(path, start=1):
            self.replays += 1
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
                "to_state": after.state_fingerprint if after else None,
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
                "observed_at": datetime.now().isoformat(),
            }
        )

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
        frontier: deque[FrontierNode] = deque([FrontierNode(path=[], depth=0)])
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
            self.max_depth_reached = max(self.max_depth_reached, node.depth)

            branch_counter += 1
            branch_id = f"branch_{branch_counter:06d}_d{node.depth:02d}"
            try:
                service, explorer, _sandbox = self._fresh_explorer(branch_id)
                state = self._replay_path(explorer, node.path)
            except Exception as exc:
                self.replay_failures += 1
                self.errors.append(
                    {"stage": "replay", "branch": branch_id, "depth": node.depth, "error": repr(exc)}
                )
                self._checkpoint(frontier)
                continue

            self.states.setdefault(state.state_fingerprint, state_record(state))
            if node.depth >= self.max_depth:
                self._checkpoint(frontier)
                continue

            controls = [
                item
                for item in state.controls
                if item.control_type in CRAWL_TYPES and item.enabled
            ]

            for control in controls:
                if self._deadline() or self.actions_attempted >= self.max_actions or len(self.states) >= self.max_states:
                    break

                pair = (state.state_fingerprint, control.identity)
                if pair in self.visited_actions:
                    self.repeats_avoided += 1
                    continue
                self.visited_actions.add(pair)
                self.actions_attempted += 1

                # Every sibling action is executed from a freshly replayed copy
                # of the same node, otherwise one action could invalidate the
                # control identities for the remaining siblings.
                sibling_id = f"action_{self.actions_attempted:07d}_d{node.depth:02d}"
                try:
                    _service2, explorer2, _sandbox2 = self._fresh_explorer(sibling_id)
                    before = self._replay_path(explorer2, node.path)
                    live_control = next(
                        (item for item in before.controls if item.identity == control.identity),
                        None,
                    )
                    if live_control is None:
                        raise RuntimeError("frontier control disappeared during fresh replay")
                    action = explorer2.activate_control(live_control.identity, self.actions_attempted)
                    self._record_transition(
                        before=before,
                        control=live_control,
                        action=action,
                        depth=node.depth,
                        path=node.path,
                    )
                    if action.success and action.state_after is not None:
                        after = action.state_after
                        self.states.setdefault(after.state_fingerprint, state_record(after))
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
                                frontier.append(FrontierNode(path=child_path, depth=node.depth + 1))
                            else:
                                self.repeats_avoided += 1
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
                self._checkpoint(frontier)

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
    )
    result = crawler.run()
    print(json.dumps(result, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
