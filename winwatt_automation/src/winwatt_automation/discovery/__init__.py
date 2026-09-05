"""Bounded, sandbox-only UI discovery. Discovery is never verification."""

from .models import CandidateCapability, DiscoveryEvidence, DiscoveryGoal, DiscoveryObservation, DiscoveryResult
from .runner import ResearchDiscoveryRunner

__all__ = ["CandidateCapability", "DiscoveryEvidence", "DiscoveryGoal", "DiscoveryObservation", "DiscoveryResult", "ResearchDiscoveryRunner"]
