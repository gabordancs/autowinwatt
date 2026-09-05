"""Deterministic local research sources; manual text is never verification."""

from .manual_index import ManualIndex
from .models import ResearchEvidence, ResearchSource

__all__ = ["ManualIndex", "ResearchEvidence", "ResearchSource"]
