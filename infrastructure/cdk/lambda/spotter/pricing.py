import boto3
import json
import logging
from datetime import datetime

logger = logging.getLogger()
pricing = boto3.client('pricing', region_name='us-east-1')

BASE_FILTERS = [
    {'Type': 'TERM_MATCH', 'Field': 'termType', 'Value': 'OnDemand'},
    {'Type': 'TERM_MATCH', 'Field': 'tenancy', 'Value': 'Shared'},
    {'Type': 'TERM_MATCH', 'Field': 'operatingSystem', 'Value': 'Linux'},
    {'Type': 'TERM_MATCH', 'Field': 'preInstalledSw', 'Value': 'NA'},
    {'Type': 'TERM_MATCH', 'Field': 'productFamily', 'Value': 'Compute Instance'},
    {'Type': 'TERM_MATCH', 'Field': 'capacitystatus', 'Value': 'Used'}
]


def get_ond_prices_via_api(region, instance_types):
    """Get on-demand prices"""
    def extract_price(instance_type):
        try:
            filters = BASE_FILTERS + [
                {"Type": "TERM_MATCH", "Field": "regionCode", "Value": region},
                {'Type': 'TERM_MATCH', 'Field': 'instanceType', 'Value': instance_type}
            ]

            response = pricing.get_products(
                ServiceCode='AmazonEC2',
                Filters=filters,
                MaxResults=1
            )

            if response['PriceList']:
                data = json.loads(response['PriceList'][0])
                for term in data['terms']['OnDemand'].values():
                    for price_dim in term['priceDimensions'].values():
                        return float(price_dim['pricePerUnit']['USD'])
            return None

        except Exception as e:
            logger.error(f"Error getting price for {instance_type}: {e}")
            return None

    prices = {
        instance_type: price
        for instance_type in instance_types
        if (price := extract_price(instance_type)) is not None
    }

    logger.info(f"Retrieved prices for {len(prices)} instance types")
    return prices
