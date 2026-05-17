"""Pure-function pipeline stages: join -> apply_policy -> score -> diversify_per_az.

No I/O, no globals — same inputs, same output."""

from __future__ import annotations

from collections import defaultdict
from dataclasses import replace
from typing import Dict, List

from .models import (
    Candidate,
    INTERRUPTION_BUCKETS,
    InterruptionInfo,
    Metadata,
    Policy,
    SpotPrice,
)


def join(
    metadata: Dict[str, Metadata],
    spot_prices: List[SpotPrice],
    interruption: Dict[str, InterruptionInfo],
    policy: Policy,
) -> List[Candidate]:
    """Merge inputs into Candidate records, taking the lowest spot price
    per (instance_type, az). Drops rows missing metadata, or missing
    interruption info unless policy.include_unknown_interruption."""
    lowest: Dict[tuple, float] = {}
    for sp in spot_prices:
        key = (sp.instance_type, sp.az)
        if key not in lowest or sp.price < lowest[key]:
            lowest[key] = sp.price

    out: List[Candidate] = []
    for (it, az), price in lowest.items():
        meta = metadata.get(it)
        if meta is None:
            continue

        info = interruption.get(it)
        if info is None and not policy.include_unknown_interruption:
            continue

        out.append(
            Candidate(
                instance_type=it,
                az=az,
                family=meta.family,
                vcpu=meta.vcpu,
                memory_gb=meta.memory_gb,
                spot_price=price,
                interruption_bucket=info.bucket if info else "unknown",
                savings_pct=info.savings_pct if info else None,
                score=0.0,
            )
        )
    return out


def apply_policy(
    candidates: List[Candidate],
    policy: Policy,
    metadata: Dict[str, Metadata],
) -> List[Candidate]:
    max_severity = INTERRUPTION_BUCKETS.index(policy.max_interruption_bucket)

    def keep(c: Candidate) -> bool:
        meta = metadata.get(c.instance_type)
        if meta is None:
            return False
        if meta.architecture not in policy.architectures:
            return False
        if policy.require_current_generation and not meta.current_generation:
            return False
        if policy.exclude_burstable and meta.burstable:
            return False
        if c.vcpu < policy.min_vcpu:
            return False
        if (
            policy.allowed_families is not None
            and c.family not in policy.allowed_families
        ):
            return False
        if c.interruption_bucket == "unknown":
            return policy.include_unknown_interruption
        return INTERRUPTION_BUCKETS.index(c.interruption_bucket) <= max_severity

    return [c for c in candidates if keep(c)]


def score(candidates: List[Candidate]) -> List[Candidate]:
    """$/vCPU score; lower is better."""
    return [
        replace(c, score=c.spot_price / max(c.vcpu, 1)) for c in candidates
    ]


def diversify_per_az(
    candidates: List[Candidate],
    policy: Policy,
) -> Dict[str, List[Candidate]]:
    """Sort within each AZ by (score asc, instance_type asc); lex tiebreak
    is what makes the output deterministic. Cap per-family, take top_n."""
    by_az: Dict[str, List[Candidate]] = defaultdict(list)
    for c in candidates:
        by_az[c.az].append(c)

    result: Dict[str, List[Candidate]] = {}
    for az, items in by_az.items():
        items.sort(key=lambda c: (c.score, c.instance_type))
        chosen: List[Candidate] = []
        family_count: Dict[str, int] = defaultdict(int)
        for c in items:
            if family_count[c.family] >= policy.max_per_family_per_az:
                continue
            chosen.append(c)
            family_count[c.family] += 1
            if len(chosen) >= policy.top_n_per_az:
                break
        if chosen:
            result[az] = chosen
    return result
