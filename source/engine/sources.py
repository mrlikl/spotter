"""DataSources Protocol + AWS-backed implementation.

The engine depends only on the Protocol; tests pass fakes."""

from __future__ import annotations

import json
import logging
import urllib.request
from datetime import datetime, timezone
from typing import Dict, List, Optional, Protocol

import boto3

from .models import INTERRUPTION_BUCKETS, InterruptionInfo, Metadata, SpotPrice

logger = logging.getLogger(__name__)

ADVISOR_URL = "https://spot-bid-advisor.s3.amazonaws.com/spot-advisor-data.json"


class DataSources(Protocol):
    def get_metadata(self) -> Dict[str, Metadata]:
        ...

    def get_spot_prices(self) -> List[SpotPrice]:
        ...

    def get_interruption(self) -> Dict[str, InterruptionInfo]:
        ...


class AwsDataSources:
    """Production sources: EC2 DescribeInstanceTypes + DescribeSpotPriceHistory
    + Spot Instance Advisor JSON feed."""

    def __init__(
        self,
        region: str,
        ec2_client=None,
        advisor_url: str = ADVISOR_URL,
        advisor_timeout: float = 10.0,
    ):
        self.region = region
        self.ec2 = ec2_client or boto3.client("ec2", region_name=region)
        self.advisor_url = advisor_url
        self.advisor_timeout = advisor_timeout

    def get_metadata(self) -> Dict[str, Metadata]:
        """Fetch current-gen spot-eligible types.

        Architecture and burstability are surfaced as fields rather than
        filtered here, so the cache is reusable across policies."""
        out: Dict[str, Metadata] = {}
        next_token: Optional[str] = None
        while True:
            params: dict = {
                "Filters": [
                    {"Name": "current-generation", "Values": ["true"]},
                    {"Name": "supported-usage-class", "Values": ["spot"]},
                ],
            }
            if next_token:
                params["NextToken"] = next_token
            resp = self.ec2.describe_instance_types(**params)
            for it in resp["InstanceTypes"]:
                out[it["InstanceType"]] = self._to_metadata(it)
            next_token = resp.get("NextToken")
            if not next_token:
                break
        logger.info("Loaded metadata for %d instance types", len(out))
        return out

    @staticmethod
    def _to_metadata(it: dict) -> Metadata:
        instance_type = it["InstanceType"]
        family = instance_type.split(".", 1)[0]
        archs = it.get("ProcessorInfo", {}).get("SupportedArchitectures", [])
        return Metadata(
            instance_type=instance_type,
            family=family,
            vcpu=it["VCpuInfo"]["DefaultVCpus"],
            memory_gb=it["MemoryInfo"]["SizeInMiB"] / 1024.0,
            architecture=archs[0] if archs else "unknown",
            current_generation=it.get("CurrentGeneration", False),
            burstable=it.get("BurstablePerformanceSupported", False),
        )

    def get_spot_prices(self) -> List[SpotPrice]:
        """Fetch the most recent spot price per (instance_type, AZ).

        StartTime=now anchors the query to the latest snapshot."""
        out: List[SpotPrice] = []
        next_token: Optional[str] = None
        while True:
            params: dict = {
                "ProductDescriptions": ["Linux/UNIX"],
                "StartTime": datetime.now(timezone.utc),
            }
            if next_token:
                params["NextToken"] = next_token
            resp = self.ec2.describe_spot_price_history(**params)
            for row in resp["SpotPriceHistory"]:
                out.append(
                    SpotPrice(
                        instance_type=row["InstanceType"],
                        az=row["AvailabilityZone"],
                        price=float(row["SpotPrice"]),
                    )
                )
            next_token = resp.get("NextToken")
            if not next_token:
                break
        logger.info("Loaded %d spot price observations", len(out))
        return out

    def get_interruption(self) -> Dict[str, InterruptionInfo]:
        """Fetch the public Spot Instance Advisor JSON.

        The 'r' field is an index into the published bucket list; 's' is
        the savings-vs-on-demand percentage we surface for display.
        """
        with urllib.request.urlopen(
            self.advisor_url, timeout=self.advisor_timeout
        ) as r:
            data = json.loads(r.read())
        region_data = (
            data.get("spot_advisor", {}).get(self.region, {}).get("Linux", {})
        )
        out: Dict[str, InterruptionInfo] = {}
        for it, info in region_data.items():
            idx = info.get("r")
            if idx is None or idx >= len(INTERRUPTION_BUCKETS):
                continue
            out[it] = InterruptionInfo(
                instance_type=it,
                bucket=INTERRUPTION_BUCKETS[idx],
                savings_pct=int(info.get("s", 0)),
            )
        logger.info(
            "Loaded interruption info for %d types in %s", len(out), self.region
        )
        return out
