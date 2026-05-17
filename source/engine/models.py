"""Data models the engine commits to.

Adding fields with defaults is back-compat. Removing or renaming requires
bumping SCHEMA_VERSION so consumers can detect a breaking change.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass
from datetime import datetime
from typing import Dict, List, Optional, Tuple

SCHEMA_VERSION = 1

# Order in this tuple is the severity index used by Spot Advisor (lower = better).
INTERRUPTION_BUCKETS: Tuple[str, ...] = ("<5%", "5-10%", "10-15%", "15-20%", ">20%")


@dataclass(frozen=True)
class Policy:
    """Frozen so the engine can derive a stable policy_hash for change detection."""

    architectures: Tuple[str, ...] = ("arm64",)
    min_vcpu: int = 4
    max_interruption_bucket: str = "10-15%"
    allowed_families: Optional[Tuple[str, ...]] = None
    exclude_burstable: bool = True
    require_current_generation: bool = True
    max_per_family_per_az: int = 2
    top_n_per_az: int = 10
    include_unknown_interruption: bool = False

    def __post_init__(self) -> None:
        if self.max_interruption_bucket not in INTERRUPTION_BUCKETS:
            raise ValueError(
                f"max_interruption_bucket must be one of {INTERRUPTION_BUCKETS}"
            )
        if self.min_vcpu < 1:
            raise ValueError("min_vcpu must be >= 1")
        if self.top_n_per_az < 1:
            raise ValueError("top_n_per_az must be >= 1")
        if self.max_per_family_per_az < 1:
            raise ValueError("max_per_family_per_az must be >= 1")
        if not self.architectures:
            raise ValueError("at least one architecture required")


@dataclass(frozen=True)
class Metadata:
    instance_type: str
    family: str
    vcpu: int
    memory_gb: float
    architecture: str
    current_generation: bool
    burstable: bool


@dataclass(frozen=True)
class SpotPrice:
    instance_type: str
    az: str
    price: float


@dataclass(frozen=True)
class InterruptionInfo:
    instance_type: str
    bucket: str
    savings_pct: int


@dataclass(frozen=True)
class Candidate:
    instance_type: str
    az: str
    family: str
    vcpu: int
    memory_gb: float
    spot_price: float
    interruption_bucket: str
    savings_pct: Optional[int]
    score: float


@dataclass
class CandidateSet:
    schema_version: int
    region: str
    generated_at: datetime
    policy_hash: str
    by_az: Dict[str, List[Candidate]]

    def to_dict(self) -> dict:
        """JSON-friendly representation for SSM / display."""
        return {
            "schema_version": self.schema_version,
            "region": self.region,
            "generated_at": self.generated_at.isoformat(),
            "policy_hash": self.policy_hash,
            "by_az": {
                az: [asdict(c) for c in cs] for az, cs in self.by_az.items()
            },
        }
