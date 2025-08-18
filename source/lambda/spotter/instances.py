import boto3
from datetime import datetime 

def describe_instance_types(ec2, next_token):
    params = {
        'Filters': [
            {
                'Name': 'current-generation',
                'Values': [
                    'true',
                ]
            },
            {
                'Name': 'supported-usage-class',
                'Values': [
                    'spot',
                ]
            },
            {
                'Name':   'processor-info.supported-architecture',
                'Values': [
                    'arm64',
                ]
            },
            {
                'Name': 'burstable-performance-supported',
                'Values': [
                    'false',
                ]
            },
        ]
    }
    if next_token and next_token != 'start':
        params['NextToken'] = next_token

    response = ec2.describe_instance_types(**params)
    return response['InstanceTypes'], response.get('NextToken', None)


def get_instance_types(region):
    ec2 = boto3.client('ec2', region_name=region)
    instances = []
    next_token = 'start'
    while next_token is not None:
        instance_info, next_token = describe_instance_types(ec2, next_token)
        instances.extend(instance_info)
    return instances


def describe_spot_price_history(ec2, instance_types, next_token):
    params = {
        'InstanceTypes': instance_types,
        'ProductDescriptions': ['Linux/UNIX'],
        'StartTime': datetime.now()
    }
    if next_token and next_token != 'start':
        params['NextToken'] = next_token

    response = ec2.describe_spot_price_history(**params)
    return response['SpotPriceHistory'], response.get('NextToken', None)


def get_spot_prices(region, instance_types):
    ec2 = boto3.client('ec2', region_name=region)
    spot_prices = []
    next_token = 'start'
    while next_token != '':
        spot_price_info, next_token = describe_spot_price_history(
            ec2, instance_types, next_token)
        spot_prices.extend(spot_price_info)
    return spot_prices
