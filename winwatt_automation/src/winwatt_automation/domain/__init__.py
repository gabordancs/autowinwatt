"""UI-independent input and result models for semantic WinWatt operations."""

from .project import PrepareRoomsInput
from .results import EvidenceItem, OperationResult
from .room import RoomInput

__all__ = ["EvidenceItem", "OperationResult", "PrepareRoomsInput", "RoomInput"]
