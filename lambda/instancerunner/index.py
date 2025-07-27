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


def get_cluster_settings(cluster_name: str) -> Dict:
    """Get cluster settings from SSM parameter"""
    param_name = f"/spotter/settings/{cluster_name}"

    try:
        response = ssm_client.get_parameter(Name=param_name)
        settings = json.loads(response['Parameter']['Value'])
        logger.info(f"Retrieved settings for cluster {cluster_name}")
        return settings
    except ssm_client.exceptions.ParameterNotFound:
        logger.error(
            f"Settings not found for cluster {cluster_name}. Run 'spotter onboard {cluster_name}' first.")
        raise Exception(
            f"Cluster {cluster_name} not onboarded. Run 'spotter onboard {cluster_name}' first.")
    except Exception as e:
        logger.error(f"Error getting settings for cluster {cluster_name}: {e}")
        raise


def get_subnet_az_mapping(subnet_ids: List[str]) -> Dict[str, str]:
    """Get AZ mapping for provided subnet IDs"""
    response = ec2_client.describe_subnets(SubnetIds=subnet_ids)
    return {
        subnet['AvailabilityZone']: subnet['SubnetId']
        for subnet in response['Subnets']
    }


def get_tag_specifications(cluster_name: str, retry_count: int = 0) -> List[Dict]:
    return [{
        'ResourceType': 'instance',
        'Tags': [
            {'Key': 'name', 'Value': f'spotter-node-{cluster_name}'},
            {'Key': f'kubernetes.io/cluster/{cluster_name}', 'Value': 'owned'},
            {'Key': 'managedby', 'Value': 'spotter'},
            {'Key': 'cluster', 'Value': cluster_name},
            {'Key': 'retrycount', 'Value': str(retry_count)}
        ]
    }]


def is_spotter_managed_instance(instance_id: str) -> Optional[str]:
    """Check if the interrupted instance was launched by Spotter and return cluster name"""
    try:
        response = ec2_client.describe_instances(InstanceIds=[instance_id])

        for reservation in response['Reservations']:
            for instance in reservation['Instances']:
                tags = {tag['Key']: tag['Value']
                        for tag in instance.get('Tags', [])}

                # Check for Spotter-specific tags
                if (tags.get('managedby') == 'spotter'):
                    cluster_name = tags.get('cluster')
                    logger.info(
                        f"Instance {instance_id} is Spotter-managed for cluster {cluster_name}")
                    return cluster_name

        logger.info(f"Instance {instance_id} is NOT Spotter-managed")
        return None

    except Exception as e:
        logger.error(f"Error checking instance {instance_id}: {e}")
        return None


def is_spot_interruption_event(event: Dict) -> Optional[Dict]:
    """Check if event is spot interruption for Spotter-managed instance"""
    try:
        if (event.get('source') == 'aws.ec2' and
                event.get('detail-type') == 'EC2 Spot Instance Interruption Warning'):

            # Extract instance ID from resources ARN
            resources = event.get('resources', [])
            if resources:
                arn = resources[0]
                instance_id = arn.split('/')[-1]  # Extract instance ID
                az = arn.split(':')[3]  # Extract AZ

                # Verify this is a Spotter-managed instance and get cluster name
                cluster_name = is_spotter_managed_instance(instance_id)
                if cluster_name:
                    logger.info(
                        f"Spot interruption for Spotter instance {instance_id} in {az} for cluster {cluster_name}")
                    return {
                        'cluster_name': cluster_name,
                        'az': az,
                        'instance_id': instance_id
                    }
                else:
                    logger.info(
                        f"Ignoring interruption for non-Spotter instance {instance_id}")
                    return None

    except Exception as e:
        logger.error(f"Error parsing event: {e}")

    return None


def get_instances_for_az(az: str) -> List[Dict]:
    """Get spot instances for specific AZ from SSM"""
    param_name = f"/spotter/prices/{az}"

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


def launch_spot_instance(instance_data: Dict, cluster_settings: Dict, retry_count: int = 0) -> Optional[str]:
    """Launch spot instance with retry logic for InsufficientCapacity"""
    instance_type = instance_data['instance_type']
    az = instance_data['az']
    max_price = instance_data['spot_price']

    launch_template_id = cluster_settings['launch_template_id']
    subnet_map = cluster_settings['subnet_map']
    cluster_name = cluster_settings['cluster_name']

    subnet_id = subnet_map.get(az)
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
                'LaunchTemplateId': launch_template_id,
                'Version': '$Latest'
            },
            MinCount=1,
            MaxCount=1,
            TagSpecifications=get_tag_specifications(cluster_name, retry_count)
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
        elif error_code == 'SpotMaxPriceTooLow':
            logger.warning(
                f"SpotMaxPriceTooLow for {instance_type} in {az}, trying next instance")
            return None
        else:
            logger.error(f"Failed to launch {instance_type} in {az}: {e}")
            raise


def launch_with_fallback(az: str, cluster_settings: Dict) -> Optional[Dict]:
    """Launch instance in AZ with fallback to next cheapest on InsufficientCapacity"""
    instances = get_instances_for_az(az)

    for i, instance_data in enumerate(instances):
        logger.info(
            f"Trying instance {i+1}/{len(instances)}: {instance_data['instance_type']}")

        instance_id = launch_spot_instance(
            instance_data, cluster_settings, retry_count=i)

        if instance_id:
            return {
                'instance_id': instance_id,
                'instance_type': instance_data['instance_type'],
                'az': az,
                'retry_count': i
            }

    logger.error(f"Failed to launch any instance in {az}")
    return None


def distribute_instances_across_azs(total_instances: int, cluster_settings: Dict) -> List[Dict]:
    """Distribute N instances across available AZs equally"""
    subnet_map = cluster_settings['subnet_map']
    available_azs = list(subnet_map.keys())

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
        interruption_info = is_spot_interruption_event(event)

        launched_instances = []

        if interruption_info:
            # Spot interruption: launch replacement in specific AZ
            cluster_name = interruption_info['cluster_name']
            az = interruption_info['az']

            logger.info(
                f"Handling spot interruption in {az} for cluster {cluster_name}")

            # Get cluster settings
            cluster_settings = get_cluster_settings(cluster_name)

            result = launch_with_fallback(az, cluster_settings)
            if result:
                launched_instances.append(result)
        else:
            # Manual invocation with cluster and count
            cluster_name = event.get('cluster')
            instance_count = int(event.get('count', 1))
            az = event.get('az')

            if not cluster_name:
                raise Exception(
                    "cluster parameter is required for manual invocation")

            # Get cluster settings
            cluster_settings = get_cluster_settings(cluster_name)

            if not az:
                logger.info(
                    f"Scaling up: launching {instance_count} instances for cluster {cluster_name}")
                instances = distribute_instances_across_azs(
                    instance_count, cluster_settings)
                for instance_data in instances:
                    result = launch_with_fallback(
                        instance_data['az'], cluster_settings)
                    if result:
                        launched_instances.append(result)
            else:
                logger.info(
                    f"Launching an instance for cluster {cluster_name} in {az}")
                for n in range(0, instance_count):
                    result = launch_with_fallback(az, cluster_settings)
                    if result:
                        launched_instances.append(result)

        response_body = {
            'message': 'Success',
            'event_type': 'spot_interruption' if interruption_info else 'manual',
            'cluster_name': interruption_info['cluster_name'] if interruption_info else event.get('cluster'),
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
