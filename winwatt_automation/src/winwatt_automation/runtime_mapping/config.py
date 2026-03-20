"""Runtime mapping performance configuration."""

from __future__ import annotations

from dataclasses import dataclass


PERFORMANCE_MODE = "fast"


@dataclass(slots=True)
class DiagnosticOptions:
    diagnostic_fast_mode: bool = False
    placeholder_traversal_focus: bool = False
    placeholder_modal_policy: str = "submenu_only"
    disable_global_process_scan_rows: bool = False
    minimize_cache_validation: bool = False
    suppress_placeholder_top_menu_relist: bool = False
    main_window_only_popup_rows: bool = False


_DIAGNOSTIC_OPTIONS = DiagnosticOptions()


def is_fast_mode() -> bool:
    return PERFORMANCE_MODE.strip().lower() == "fast"


def configure_diagnostics(
    *,
    diagnostic_fast_mode: bool = False,
    placeholder_traversal_focus: bool = False,
    placeholder_modal_policy: str = "submenu_only",
) -> None:
    _DIAGNOSTIC_OPTIONS.diagnostic_fast_mode = diagnostic_fast_mode
    _DIAGNOSTIC_OPTIONS.placeholder_traversal_focus = placeholder_traversal_focus
    _DIAGNOSTIC_OPTIONS.placeholder_modal_policy = str(placeholder_modal_policy or "submenu_only").strip().lower()
    _DIAGNOSTIC_OPTIONS.disable_global_process_scan_rows = diagnostic_fast_mode
    _DIAGNOSTIC_OPTIONS.minimize_cache_validation = diagnostic_fast_mode
    _DIAGNOSTIC_OPTIONS.suppress_placeholder_top_menu_relist = diagnostic_fast_mode or placeholder_traversal_focus
    _DIAGNOSTIC_OPTIONS.main_window_only_popup_rows = diagnostic_fast_mode


def diagnostic_options() -> DiagnosticOptions:
    return _DIAGNOSTIC_OPTIONS


def is_diagnostic_fast_mode() -> bool:
    return _DIAGNOSTIC_OPTIONS.diagnostic_fast_mode


def is_placeholder_traversal_focus_mode() -> bool:
    return _DIAGNOSTIC_OPTIONS.placeholder_traversal_focus


def placeholder_modal_policy() -> str:
    return _DIAGNOSTIC_OPTIONS.placeholder_modal_policy
