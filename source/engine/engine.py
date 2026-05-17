"""Engine orchestrator. Sources is the only impure boundary; fails closed
if metadata or spot prices are missing — degraded mode hides problems."""

from __future__ import annotations

import hashlib
import json
import logging
from concurrent.futures import ThreadPoolExecutor
from dataclasses import asdict
from datetime import datetime, timezone

from .models import CandidateSet, Policy, SCHEMA_VERSION
from .pipeline import apply_policy, diversify_per_az, join, score
from .sources import DataSources

logger = logging.getLogger(__name__)


class EngineError(Exception):
    """Raised when the engine cannot produce a valid CandidateSet."""


def find_candidates(
    region: str,
    policy: Policy,
    sources: DataSources,
) -> CandidateSet:
    """Produce a per-AZ ranked, diversified list of viable spot candidates."""
    with ThreadPoolExecutor(max_workers=3) as pool:
        f_meta = pool.submit(sources.get_metadata)
        f_prices = pool.submit(sources.get_spot_prices)
        f_intr = pool.submit(sources.get_interruption)
        metadata = f_meta.result()
        prices = f_prices.result()
        interruption = f_intr.result()

    if not metadata:
        raise EngineError("instance type metadata is empty")
    if not prices:
        raise EngineError("spot price data is empty")

    candidates = join(metadata, prices, interruption, policy)
    candidates = apply_policy(candidates, policy, metadata)
    candidates = score(candidates)
    by_az = diversify_per_az(candidates, policy)

    cs = CandidateSet(
        schema_version=SCHEMA_VERSION,
        region=region,
        generated_at=datetime.now(timezone.utc),
        policy_hash=_hash_policy(policy),
        by_az=by_az,
    )
    logger.info(
        "Produced CandidateSet: %d AZs, %d total candidates",
        len(by_az),
        sum(len(v) for v in by_az.values()),
    )
    return cs


def _hash_policy(policy: Policy) -> str:
    blob = json.dumps(asdict(policy), sort_keys=True, default=list).encode()
    return hashlib.sha256(blob).hexdigest()[:12]
