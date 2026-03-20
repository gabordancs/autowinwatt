"""Small UI object caching primitives for runtime mapping."""

from __future__ import annotations

import time
from dataclasses import dataclass
from typing import Any, Callable


class UIObjectCache:
    def __init__(self) -> None:
        self._store: dict[tuple[Any, ...], tuple[float, Any]] = {}

    def get_or_query(self, locator: tuple[Any, ...], query: Callable[[], Any], *, ttl_s: float = 0.6) -> Any:
        now = time.monotonic()
        cached = self._store.get(locator)
        if cached and now - cached[0] <= ttl_s:
            return cached[1]
        value = query()
        self._store[locator] = (now, value)
        return value

    def clear(self) -> None:
        self._store.clear()


@dataclass
class PopupState:
    current_menu_path: tuple[str, ...] | None = None
    popup_handle: int | None = None
    popup_rows: list[dict[str, Any]] | None = None
    runtime_state_reset_required: bool = False

