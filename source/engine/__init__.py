"""Spotter engine: produce ranked, diversified spot candidates per AZ.

Public surface: find_candidates(region, policy, sources) -> CandidateSet.
Everything else in this package is internal and may change.
"""

from .engine import EngineError, find_candidates
from .models import (
    Candidate,
    CandidateSet,
    INTERRUPTION_BUCKETS,
    InterruptionInfo,
    Metadata,
    Policy,
    SCHEMA_VERSION,
    SpotPrice,
)
from .sources import AwsDataSources, DataSources

__all__ = [
    "AwsDataSources",
    "Candidate",
    "CandidateSet",
    "DataSources",
    "EngineError",
    "INTERRUPTION_BUCKETS",
    "InterruptionInfo",
    "Metadata",
    "Policy",
    "SCHEMA_VERSION",
    "SpotPrice",
    "find_candidates",
]
