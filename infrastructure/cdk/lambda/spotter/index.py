import json
import os
import logging
import boto3
from typing import Dict, List
from collections import defaultdict
from instances import get_spot_prices, get_instance_types
from pricing import get_ond_prices_via_api

logger = logging.getLogger()
logger.setLevel("INFO")

# Environment variables
REGION = os.environ.get('AWS_REGION')
MIN_SAVINGS_PERCENT = float(os.environ.get('MIN_SAVINGS_PERCENT'))
MAX_PODS = 110

# AWS clients
ssm_client = boto3.client('ssm')


def get_filtered_instance_types() -> List[str]:
    """Get filtered instance types"""
    logger.info("Getting filtered instance types...")
    instances = get_instance_types(REGION)

    filtered = [
        instance['InstanceType']
        for instance in instances
        if (net := instance.get('NetworkInfo', {})) and
           (net.get('MaximumNetworkInterfaces', 0) *
            net.get('Ipv4AddressesPerInterface', 0)) < MAX_PODS
    ]

    logger.info(f"Filtered to {len(filtered)} instance types")
    return filtered


def find_top_per_az(instance_types: List[str]) -> Dict[str, List[Dict]]:
    """Find top 6 instances per AZ"""
    logger.info("Getting spot prices...")
    spot_prices_raw = get_spot_prices(REGION, instance_types)

    logger.info("Getting on-demand prices...")
    on_demand_prices = get_ond_prices_via_api(REGION, instance_types)

    az_prices = defaultdict(dict)
    for price in spot_prices_raw:
        instance_type = price['InstanceType']
        spot_price = float(price['SpotPrice'])
        az = price['AvailabilityZone']

        # Keep lowest price per instance type per AZ
        if instance_type not in az_prices[az] or spot_price < az_prices[az][instance_type]:
            az_prices[az][instance_type] = spot_price

    results_by_az = {
        az: sorted([
            {'instance_type': instance_type, 'spot_price': spot_price}
            for instance_type, spot_price in prices.items()
            if instance_type in on_demand_prices and
            ((on_demand_prices[instance_type] - spot_price) /
             on_demand_prices[instance_type] * 100) >= MIN_SAVINGS_PERCENT
        ], key=lambda x: x['spot_price'])[:6]
        for az, prices in az_prices.items()
    }

    for az, results in results_by_az.items():
        logger.info(f"AZ {az}: Found {len(results)} top instances")

    return results_by_az


def store_in_ssm_per_az(results_by_az: Dict[str, List[Dict]]) -> None:
    """Store results in SSM with one parameter per AZ"""

    ssm_operations = {
        f"/spotter/spot/{az}": json.dumps(results)
        for az, results in results_by_az.items()
        if results
    }

    for param_name, param_value in ssm_operations.items():
        ssm_client.put_parameter(
            Name=param_name,
            Value=param_value,
            Type='String',
            Overwrite=True
        )

    logger.info(f"Stored parameters for {len(ssm_operations)} AZs")


def lambda_handler(event, context):
    """Lambda handler"""
    try:
        instance_types = get_filtered_instance_types()
        if not instance_types:
            return {'statusCode': 200, 'body': json.dumps({'message': 'No instances found'})}

        results_by_az = find_top_per_az(instance_types)
        store_in_ssm_per_az(results_by_az)

        response_body = {
            'message': 'Success',
            'azs_processed': len(results_by_az),
            'total_instances': sum(len(results) for results in results_by_az.values())
        }

        return {'statusCode': 200, 'body': json.dumps(response_body)}

    except Exception as e:
        logger.error(f"Error: {str(e)}")
        return {'statusCode': 500, 'body': json.dumps({'error': str(e)})}
