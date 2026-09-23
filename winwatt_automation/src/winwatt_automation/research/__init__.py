"""Deterministic local research sources; manual text is never verification."""

from .models import ResearchEvidence, ResearchSource

__all__ = ["ManualIndex", "ResearchEvidence", "ResearchSource"]


def __getattr__(name: str):
    """Keep PDF parsing optional for non-manual CLI commands."""
    if name == "ManualIndex":
        from .manual_index import ManualIndex
        return ManualIndex
    raise AttributeError(name)
