"""AWS EC2 client utilities."""

import boto3
from typing import Dict, Any, List
from rich.console import Console
from rich.table import Table
from rich.prompt import Confirm
from rich.progress import Progress, SpinnerColumn, TextColumn
from botocore.exceptions import ClientError

console = Console()


class EC2Client:
    """AWS EC2 client wrapper."""

    def __init__(self, region: str):
        self.region = region
        self.ec2 = boto3.client('ec2', region_name=region)

    def get_spotter_instances(self, cluster_name: str) -> List[Dict]:
        """Get all running Spotter-managed instances for a cluster."""
        try:
            response = self.ec2.describe_instances(
                Filters=[
                    {'Name': 'tag:managedby', 'Values': ['spotter']},
                    {'Name': 'tag:cluster', 'Values': [cluster_name]},
                    {'Name': 'instance-state-name',
                        'Values': ['running', 'pending']}
                ]
            )

            instances = []
            for reservation in response['Reservations']:
                for instance in reservation['Instances']:
                    instances.append({
                        'instance_id': instance['InstanceId'],
                        'instance_type': instance['InstanceType'],
                        'availability_zone': instance['Placement']['AvailabilityZone'],
                        'state': instance['State']['Name'],
                        'launch_time': instance['LaunchTime']
                    })

            return sorted(instances, key=lambda x: x['launch_time'])
        except Exception as e:
            console.print(f"[red]Failed to get instances: {e}[/red]")
            raise

    def terminate_instances(self, instances_to_terminate: List[Dict]) -> bool:
        """Terminate specified instances."""

        if not instances_to_terminate:
            return True

        terminate_count = len(instances_to_terminate)
        console.print(
            f"[red]Will terminate {terminate_count} instances:[/red]")

        table = Table()
        table.add_column("Instance ID", style="cyan")
        table.add_column("Type", style="green")
        table.add_column("AZ", style="yellow")
        table.add_column("State", style="magenta")
        table.add_column("Launch Time", style="blue")

        for instance in instances_to_terminate:
            table.add_row(
                instance['instance_id'],
                instance['instance_type'],
                instance['availability_zone'],
                instance['state'],
                instance['launch_time'].strftime('%Y-%m-%d %H:%M:%S')
            )

        console.print(table)

        console.print(
            f"[red]⚠️  This will terminate {terminate_count} instances![/red]")
        if not Confirm.ask("Are you sure?"):
            console.print("[yellow]Termination cancelled[/yellow]")
            return False

        # Terminate instances
        instance_ids = [instance['instance_id']
                        for instance in instances_to_terminate]

        try:
            with Progress(
                SpinnerColumn(),
                TextColumn("[progress.description]{task.description}"),
                console=console,
            ) as progress:
                task = progress.add_task(
                    "Terminating instances...", total=None)

                self.ec2.terminate_instances(InstanceIds=instance_ids)

                progress.update(
                    task, description="Instances termination initiated")

            console.print(
                f"[green]✅ Initiated termination of {terminate_count} instances[/green]")
            return True

        except Exception as e:
            console.print(f"[red]Failed to terminate instances: {e}[/red]")
            raise

    def terminate_cluster_instances(self, cluster_name: str) -> bool:
        """Terminate all running instances for a cluster."""
        console.print(
            f"[blue]Terminating instances for cluster {cluster_name}...[/blue]")

        try:
            # Find instances with the cluster tag
            response = self.ec2.describe_instances(
                Filters=[
                    {
                        'Name': 'tag:cluster',
                        'Values': [cluster_name]
                    },
                    {
                        'Name': 'tag:managedby',
                        'Values': ['spotter']
                    },
                    {
                        'Name': 'instance-state-name',
                        'Values': ['running', 'pending', 'stopping', 'stopped']
                    }
                ]
            )

            instance_ids = []
            for reservation in response['Reservations']:
                for instance in reservation['Instances']:
                    instance_ids.append(instance['InstanceId'])

            if instance_ids:
                console.print(
                    f"[yellow]Found {len(instance_ids)} instances to terminate[/yellow]")
                self.ec2.terminate_instances(InstanceIds=instance_ids)
                console.print(
                    f"[green]✅ Terminated {len(instance_ids)} instances[/green]")
            else:
                console.print(
                    "[green]✅ No instances found to terminate[/green]")

            return True

        except Exception as e:
            console.print(
                f"[yellow]Failed to terminate instances: {e}[/yellow]")
            return False

    def list_vpc_subnets(self, vpc_id: str) -> List[Dict[str, Any]]:
        """List available subnets in the VPC."""
        try:
            response = self.ec2.describe_subnets(
                Filters=[
                    {'Name': 'vpc-id', 'Values': [vpc_id]},
                    {'Name': 'state', 'Values': ['available']}
                ]
            )

            subnets = []
            for subnet in response['Subnets']:
                name = None
                for tag in subnet.get('Tags', []):
                    if tag['Key'] == 'Name':
                        name = tag['Value']
                        break

                subnets.append({
                    'subnet_id': subnet['SubnetId'],
                    'availability_zone': subnet['AvailabilityZone'],
                    'cidr_block': subnet['CidrBlock'],
                    'name': name or '-'
                })

            return sorted(subnets, key=lambda x: x['availability_zone'])
        except ClientError as e:
            raise Exception(f"Failed to list subnets: {e}")
    
    def get_instances_in_az(self, cluster_name: str, az: str, count: int) -> List[Dict]:
        """Get instances to terminate from a specific AZ."""
        try:
            response = self.ec2.describe_instances(
                Filters=[
                    {
                        'Name': 'tag:cluster',
                        'Values': [cluster_name]
                    },
                    {
                        'Name': 'tag:managedby',
                        'Values': ['spotter']
                    },
                    {
                        'Name': 'availability-zone',
                        'Values': [az]
                    },
                    {
                        'Name': 'instance-state-name',
                        'Values': ['running']
                    }
                ]
            )
            
            instances = []
            for reservation in response['Reservations']:
                for instance in reservation['Instances']:
                    instances.append({
                        'instance_id': instance['InstanceId'],
                        'launch_time': instance['LaunchTime']
                    })
            
            # Sort by launch time (oldest first) and return the requested count
            instances.sort(key=lambda x: x['launch_time'])
            return instances[:count]
            
        except Exception as e:
            console.print(f"[red]Failed to get instances in {az}: {e}[/red]")
            return []
    
    def terminate_instances_by_ids(self, instance_ids: List[str]) -> bool:
        """Terminate instances by their IDs."""
        try:
            self.ec2.terminate_instances(InstanceIds=instance_ids)
            return True
        except Exception as e:
            console.print(f"[red]Failed to terminate instances: {e}[/red]")
            return False
