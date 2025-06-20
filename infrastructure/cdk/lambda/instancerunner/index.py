import json
import os
import logging
import boto3
from typing import Dict, List, Optional

logger = logging.getLogger()
logger.setLevel("INFO")

# AWS clients
ec2_client = boto3.client('ec2')
ssm_client = boto3.client('ssm')

EKS_CLUSTER_NAME = os.environ.get('EKS_CLUSTER_NAME')
LAUNCH_TEMPLATE_ID = os.environ.get('LAUNCH_TEMPLATE_ID')
DESIRED_INSTANCE_COUNT = int(os.environ.get('DESIRED_INSTANCE_COUNT', '1'))


def get_subnet_az_mapping(subnet_ids: List[str]) -> Dict[str, str]:
    """Get AZ mapping for provided subnet IDs"""
    response = ec2_client.describe_subnets(SubnetIds=subnet_ids)
    return {
        subnet['AvailabilityZone']: subnet['SubnetId']
        for subnet in response['Subnets']
    }


SUBNET_IDS = os.environ.get('SUBNET_IDS', '').split(',')
SUBNET_MAP = get_subnet_az_mapping(SUBNET_IDS) if SUBNET_IDS != [''] else {}


def get_tag_specifications(retry_count: int = 0) -> List[Dict]:
    return [{
        'ResourceType': 'instance',
        'Tags': [
            {'Key': 'Name', 'Value': f'Spotter-Node-{EKS_CLUSTER_NAME}'},
            {'Key': f'kubernetes.io/cluster/{EKS_CLUSTER_NAME}', 'Value': 'owned'},
            {'Key': 'ManagedBy', 'Value': 'Spotter'},
            {'Key': 'RetryCount', 'Value': str(retry_count)}
        ]
    }]


def is_spotter_managed_instance(instance_id: str) -> bool:
    """Check if the interrupted instance was launched by Spotter"""
    try:
        response = ec2_client.describe_instances(InstanceIds=[instance_id])

        for reservation in response['Reservations']:
            for instance in reservation['Instances']:
                tags = {tag['Key']: tag['Value']
                        for tag in instance.get('Tags', [])}

                # Check for Spotter-specific tags
                if (tags.get('ManagedBy') == 'Spotter' and
                        tags.get(f'kubernetes.io/cluster/{EKS_CLUSTER_NAME}') == 'owned'):
                    logger.info(f"Instance {instance_id} is Spotter-managed")
                    return True

        logger.info(f"Instance {instance_id} is NOT Spotter-managed")
        return False

    except Exception as e:
        logger.error(f"Error checking instance {instance_id}: {e}")
        return False


def is_spot_interruption_event(event: Dict) -> Optional[str]:
    """Check if event is spot interruption for Spotter-managed instance"""
    try:
        if (event.get('source') == 'aws.ec2' and
                event.get('detail-type') == 'EC2 Spot Instance Interruption Warning'):

            # Extract instance ID and AZ from resources ARN
            resources = event.get('resources', [])
            if resources:
                arn = resources[0]
                instance_id = arn.split('/')[-1]  # Extract instance ID
                az = arn.split(':')[3]  # Extract AZ

                # Verify this is a Spotter-managed instance
                if is_spotter_managed_instance(instance_id):
                    logger.info(
                        f"Spot interruption for Spotter instance {instance_id} in {az}")
                    return az
                else:
                    logger.info(
                        f"Ignoring interruption for non-Spotter instance {instance_id}")
                    return None

    except Exception as e:
        logger.error(f"Error parsing event: {e}")

    return None


def get_instances_for_az(az: str) -> List[Dict]:
    """Get spot instances for specific AZ from SSM"""
    param_name = f"/spotter/spot/{az}"

    try:
        response = ssm_client.get_parameter(Name=param_name)
        instances = json.loads(response['Parameter']['Value'])
        return [{**instance, 'az': az} for instance in instances]

    except ssm_client.exceptions.ParameterNotFound:
        logger.warning(f"No instances found for AZ {az}")
        return []
    except Exception as e:
        logger.error(f"Error getting instances for {az}: {e}")
        return []


def get_top_instance_per_az() -> List[Dict]:
    """Get top (cheapest) instance from each AZ"""
    instances = [
        az_instances[0]
        for az in SUBNET_MAP.keys()
        if (az_instances := get_instances_for_az(az))
    ]

    logger.info(f"Selected 1 instance from each of {len(instances)} AZs")
    return instances


def launch_spot_instance(instance_data: Dict, retry_count: int = 0) -> Optional[str]:
    """Launch spot instance with retry logic for InsufficientCapacity"""
    instance_type = instance_data['instance_type']
    az = instance_data['az']
    max_price = instance_data['spot_price']

    subnet_id = SUBNET_MAP.get(az)
    if not subnet_id:
        logger.error(f"No subnet found for AZ {az}")
        return None

    try:
        response = ec2_client.run_instances(
            InstanceType=instance_type,
            SubnetId=subnet_id,
            InstanceMarketOptions={
                'MarketType': 'spot',
                'SpotOptions': {
                    'MaxPrice': str(max_price),
                    'InstanceInterruptionBehavior': 'terminate',
                    'SpotInstanceType': 'one-time'
                }
            },
            LaunchTemplate={
                'LaunchTemplateId': LAUNCH_TEMPLATE_ID,
                'Version': '$Latest'
            },
            MinCount=1,
            MaxCount=1,
            TagSpecifications=get_tag_specifications(retry_count)
        )

        instance_id = response['Instances'][0]['InstanceId']
        logger.info(f"Launched {instance_type} in {az}: {instance_id}")
        return instance_id

    except Exception as e:
        error_code = getattr(e, 'response', {}).get(
            'Error', {}).get('Code', '')

        if error_code == 'InsufficientInstanceCapacity':
            logger.warning(
                f"InsufficientCapacity for {instance_type} in {az}, trying next instance")
            return None
        else:
            logger.error(f"Failed to launch {instance_type} in {az}: {e}")
            raise


def launch_with_fallback(az: str) -> Optional[Dict]:
    """Launch instance in AZ with fallback to next cheapest on InsufficientCapacity"""
    instances = get_instances_for_az(az)

    for i, instance_data in enumerate(instances):
        logger.info(
            f"Trying instance {i+1}/{len(instances)}: {instance_data['instance_type']}")

        instance_id = launch_spot_instance(instance_data, retry_count=i)

        if instance_id:
            return {
                'instance_id': instance_id,
                'instance_type': instance_data['instance_type'],
                'az': az,
                'retry_count': i
            }

    logger.error(f"Failed to launch any instance in {az}")
    return None


def distribute_instances_across_azs(total_instances: int) -> List[Dict]:
    """Distribute N instances across available AZs equally"""
    available_azs = list(SUBNET_MAP.keys())
    if not available_azs:
        logger.error("No available AZs found")
        return []

    # Calculate distribution
    instances_per_az = total_instances // len(available_azs)
    extra_instances = total_instances % len(available_azs)

    logger.info(
        f"Distributing {total_instances} instances across {len(available_azs)} AZs")
    logger.info(
        f"Base: {instances_per_az} per AZ, Extra: {extra_instances} instances")

    distributed_instances = []

    for i, az in enumerate(available_azs):
        # Base instances + 1 extra for first few AZs
        az_instance_count = instances_per_az + \
            (1 if i < extra_instances else 0)

        if az_instance_count > 0:
            az_instances = get_instances_for_az(az)
            if az_instances:
                # Add multiple instances for this AZ
                for j in range(az_instance_count):
                    distributed_instances.append(
                        az_instances[0])  # Use cheapest

        logger.info(f"AZ {az}: {az_instance_count} instances")

    logger.info(f"Total distributed: {len(distributed_instances)} instances")
    return distributed_instances


def lambda_handler(event, context):
    """Lambda handler"""
    try:
        logger.info("Starting Instance Runner")
        logger.info(f"Event: {json.dumps(event)}")

        # Check if this is a spot interruption
        interrupted_az = is_spot_interruption_event(event)

        launched_instances = []

        if interrupted_az:
            # Spot interruption: launch replacement in specific AZ
            logger.info(f"Handling spot interruption in {interrupted_az}")
            result = launch_with_fallback(interrupted_az)
            if result:
                launched_instances.append(result)
        else:
            # Launch N instances distributed across AZs
            instance_count = int(
                event.get('instance_count', DESIRED_INSTANCE_COUNT))
            logger.info(
                f"Initial run: launching {instance_count} instances distributed across AZs")
            instances = distribute_instances_across_azs(instance_count)

            for instance_data in instances:
                result = launch_with_fallback(instance_data['az'])
                if result:
                    launched_instances.append(result)

        response_body = {
            'message': 'Success',
            'event_type': 'spot_interruption' if interrupted_az else 'initial',
            'launched_instances': launched_instances,
            'total_launched': len(launched_instances)
        }
        return {'statusCode': 200, 'body': json.dumps(response_body)}

    except Exception as e:
        logger.error(f"Handler error: {str(e)}")
        return {
            'statusCode': 500,
            'body': json.dumps({'error': str(e)})
        }
