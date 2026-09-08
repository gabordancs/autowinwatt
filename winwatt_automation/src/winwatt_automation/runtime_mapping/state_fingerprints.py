"""Stable, audit-friendly UI state fingerprints used by mapping tools."""
from __future__ import annotations

import json
from hashlib import sha1
from typing import Any


def semantic_state_fingerprint(state: Any) -> str:
    """Fingerprint navigation-relevant UI structure, not session noise."""
    controls = sorted(
        (
            item.control_type,
            item.class_name,
            item.caption or "",
            item.caption_source,
            item.parent_identity or "",
            item.ordinal if item.ordinal is not None else -1,
            bool(item.enabled),
        )
        for item in state.controls
    )
    material = json.dumps({"class": state.class_name, "controls": controls}, ensure_ascii=False, separators=(",", ":"))
    return sha1(material.encode("utf-8")).hexdigest()[:16]
