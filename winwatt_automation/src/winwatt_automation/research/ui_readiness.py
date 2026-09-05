from __future__ import annotations

import time
from typing import Any

from pydantic import BaseModel


class UIReadinessResult(BaseModel):
    ready: bool
    reason: str
    attempts: int
    elapsed_ms: int
    control_count: int
    fingerprint: str | None = None
    frontier_fingerprint: str | None = None
    failed_predicate: str | None = None
    samples: list[dict[str, Any]] = []
    model_config = {"extra": "forbid"}


class UIReadinessRecovery(BaseModel):
    recovered: bool
    attempts: int
    elapsed_ms: int
    observed_reasons: list[str]
    observed_fingerprints: list[str] = []
    final_reason: str
    model_config = {"extra": "forbid"}


def wait_for_ui_ready(explorer: Any, *, timeout_seconds: float = 15.0, interval_seconds: float = 0.35) -> tuple[UIReadinessResult, Any | None]:
    """Return only a non-empty, two-poll stable UIA state.

    Empty startup trees are not semantic navigation states and must never be
    persisted or compared against a route's expected state.
    """
    started = time.monotonic()
    attempts = 0
    previous = None
    previous_probe: dict[str, Any] | None = None
    samples: list[dict[str, Any]] = []
    last_count = 0
    while time.monotonic() - started < timeout_seconds:
        attempts += 1
        try:
            snapshot = explorer.inspect_window()
        except Exception as exc:
            return UIReadinessResult(ready=False, reason=f"window_resolution_error:{type(exc).__name__}", attempts=attempts, elapsed_ms=int((time.monotonic()-started)*1000), control_count=last_count, failed_predicate="snapshot_capture", samples=samples), None
        controls = list(getattr(snapshot, "controls", []))
        last_count = len(controls)
        probe = _probe_snapshot(explorer, snapshot, started)
        if previous_probe is not None:
            probe["diff_from_previous"] = _snapshot_diff(previous_probe, probe)
        samples.append(probe)
        if not controls:
            previous = None
            previous_probe = None
            time.sleep(interval_seconds)
            continue
        if previous is not None and previous.state_fingerprint == snapshot.state_fingerprint:
            return UIReadinessResult(ready=True, reason="stable_nonempty_snapshot", attempts=attempts, elapsed_ms=int((time.monotonic()-started)*1000), control_count=len(controls), fingerprint=snapshot.state_fingerprint, frontier_fingerprint=probe["frontier_fingerprint"], samples=samples), snapshot
        # Owner-drawn popups can churn unrelated UIA descendants while their
        # safe, observed frontier controls remain stable. This is not a blind
        # pass: same process/window plus the same nonempty actionable set is
        # required, and the executor revalidates identities immediately.
        if previous_probe is not None and _frontier_is_stable(previous_probe, probe):
            return UIReadinessResult(ready=True, reason="stable_actionable_frontier", attempts=attempts, elapsed_ms=int((time.monotonic()-started)*1000), control_count=len(controls), fingerprint=snapshot.state_fingerprint, frontier_fingerprint=probe["frontier_fingerprint"], samples=samples), snapshot
        previous = snapshot
        previous_probe = probe
        time.sleep(interval_seconds)
    predicate = "zero_controls" if last_count == 0 else "exact_snapshot_and_actionable_frontier_changed"
    return UIReadinessResult(ready=False, reason="ui_not_ready:zero_controls" if last_count == 0 else "ui_not_ready:unstable", attempts=attempts, elapsed_ms=int((time.monotonic()-started)*1000), control_count=last_count, failed_predicate=predicate, samples=samples), None


def _probe_snapshot(explorer: Any, snapshot: Any, started: float) -> dict[str, Any]:
    controls = list(getattr(snapshot, "controls", []))
    actionable = [f"{item.control_type}:{item.identity}" for item in controls if getattr(item, "enabled", False) and getattr(item, "control_type", "") in {"Button", "TabItem", "ListItem", "ComboBox", "TreeItem", "MenuItem", "Edit"}]
    popup = [item.identity for item in controls if getattr(item, "control_type", "") == "MenuItem" and not getattr(item, "caption", "")]
    window = getattr(explorer, "window", None)
    metadata: dict[str, Any] = {"timestamp_ms": int((time.monotonic()-started)*1000), "fingerprint": snapshot.state_fingerprint, "control_count": len(controls), "window_identity": getattr(snapshot, "identity", None), "window_title": getattr(snapshot, "title", None), "window_class": getattr(snapshot, "class_name", None), "actionable_controls": sorted(actionable), "frontier_fingerprint": str(hash(tuple(sorted(actionable)))), "popup_menu_identities": sorted(popup), "popup_menu_present": bool(popup)}
    try:
        metadata["window_handle"] = window.handle
        metadata["window_process_id"] = window.process_id()
    except Exception:
        metadata["window_handle"] = None; metadata["window_process_id"] = None
    try:
        from winwatt_automation.runtime_mapping.mdi_state_model import active_mdi_title
        metadata["active_mdi_title"] = active_mdi_title()
    except Exception:
        metadata["active_mdi_title"] = None
    return metadata


def _snapshot_diff(previous: dict[str, Any], current: dict[str, Any]) -> dict[str, Any]:
    prior = set(previous["actionable_controls"]); now = set(current["actionable_controls"])
    return {"fingerprint_a": previous["fingerprint"], "fingerprint_b": current["fingerprint"], "controls_added": sorted(now-prior), "controls_removed": sorted(prior-now), "control_count_changed": previous["control_count"] != current["control_count"], "properties_changed": {"active_mdi_title": (previous.get("active_mdi_title"), current.get("active_mdi_title")), "popup_menu_present": (previous["popup_menu_present"], current["popup_menu_present"])}}


def _frontier_is_stable(previous: dict[str, Any], current: dict[str, Any]) -> bool:
    return bool(previous["actionable_controls"]) and previous["window_process_id"] == current["window_process_id"] and previous["window_identity"] == current["window_identity"] and previous["frontier_fingerprint"] == current["frontier_fingerprint"] and previous["popup_menu_present"] == current["popup_menu_present"]


def recover_transient_ui_readiness(explorer: Any, *, retries: int = 5, backoff_seconds: tuple[float, ...] = (0.5, 1.0, 1.5, 2.0, 3.0)) -> tuple[UIReadinessResult, Any | None, UIReadinessRecovery]:
    """Bounded recovery after an action has left UIA temporarily unstable.

    Only the explicit unstable condition is recoverable. Missing windows,
    empty trees and window-resolution failures remain fail-closed.
    """
    started = time.monotonic()
    reasons: list[str] = []
    fingerprints: list[str] = []
    last = UIReadinessResult(ready=False, reason="ui_not_ready:unstable", attempts=0, elapsed_ms=0, control_count=0)
    for attempt in range(retries):
        time.sleep(backoff_seconds[min(attempt, len(backoff_seconds) - 1)])
        last, snapshot = wait_for_ui_ready(explorer, timeout_seconds=4.0, interval_seconds=0.35)
        reasons.append(last.reason)
        if last.fingerprint:
            fingerprints.append(last.fingerprint)
        if last.ready:
            return last, snapshot, UIReadinessRecovery(recovered=True, attempts=attempt + 1, elapsed_ms=int((time.monotonic()-started)*1000), observed_reasons=reasons, observed_fingerprints=fingerprints, final_reason=last.reason)
        if last.reason != "ui_not_ready:unstable":
            break
    return last, None, UIReadinessRecovery(recovered=False, attempts=len(reasons), elapsed_ms=int((time.monotonic()-started)*1000), observed_reasons=reasons, observed_fingerprints=fingerprints, final_reason=last.reason)
