"""AWS EKS client utilities."""

import boto3
from typing import Dict, Any, List
from botocore.exceptions import ClientError
from rich.console import Console

console = Console()


class EKSClient:
    """AWS EKS client wrapper."""

    def __init__(self, region: str):
        self.region = region
        self.eks = boto3.client('eks', region_name=region)
        self.ec2 = boto3.client('ec2', region_name=region)

    def get_cluster_details(self, cluster_name: str) -> Dict[str, Any]:
        """Get EKS cluster details needed for deployment."""
        try:
            response = self.eks.describe_cluster(name=cluster_name)
            cluster = response['cluster']

            return {
                'endpoint': cluster['endpoint'],
                'ca_data': cluster['certificateAuthority']['data'],
                'service_cidr': cluster['kubernetesNetworkConfig']['serviceIpv4Cidr'],
                'cluster_sg': cluster['resourcesVpcConfig']['clusterSecurityGroupId'],
                'vpc_id': cluster['resourcesVpcConfig']['vpcId'],
                'version': cluster['version']
            }
        except ClientError as e:
            raise Exception(f"Failed to get cluster details: {e}")

    def handle_access_entry(self, cluster_name: str, node_role_arn: str) -> None:
        """Handle EKS access entry creation for the node role."""
        console.print("[blue]Configuring EKS cluster access...[/blue]")

        try:
            # Get cluster access config
            cluster_response = self.eks.describe_cluster(name=cluster_name)
            access_config = cluster_response['cluster'].get('accessConfig', {})
            authentication_mode = access_config.get('authenticationMode')

            console.print(
                f"[yellow]Cluster authentication mode: {authentication_mode}[/yellow]")

            # Only proceed if cluster uses API or API_AND_CONFIG_MAP
            if authentication_mode in ['API', 'API_AND_CONFIG_MAP']:
                console.print(f"[cyan]Node role ARN: {node_role_arn}[/cyan]")

                # Check if access entry already exists
                try:
                    self.eks.describe_access_entry(
                        clusterName=cluster_name,
                        principalArn=node_role_arn
                    )
                    console.print(
                        "[green]✅ Access entry already exists[/green]")
                    return
                except self.eks.exceptions.ResourceNotFoundException:
                    # Access entry doesn't exist, we need to create it
                    pass

                # Create the access entry
                try:
                    self.eks.create_access_entry(
                        clusterName=cluster_name,
                        principalArn=node_role_arn,
                        type='EC2_LINUX'
                    )
                    console.print(
                        "[green]✅ Created EKS access entry for node role[/green]")
                except Exception as e:
                    console.print(
                        f"[yellow]Failed to create access entry automatically {e}[/yellow]")

            elif authentication_mode == 'CONFIG_MAP':
                console.print(
                    "[yellow]Cluster uses CONFIG_MAP authentication mode[/yellow]")
                console.print(
                    "[yellow]You may need to update the aws-auth ConfigMap manually[/yellow]")
                console.print(
                    "[cyan]See: https://docs.aws.amazon.com/eks/latest/userguide/auth-configmap.html[/cyan]")

        except Exception as e:
            console.print(
                f"[yellow]Could not check cluster access configuration: {e}[/yellow]")
            console.print(
                "[yellow]You may need to configure node access manually[/yellow]")
            
    def delete_access_entry(self, cluster_name: str, node_role_arn: str) -> None:
        """Handle EKS access entry creation for the node role."""
        console.print("[blue]Removing EKS Access entry from cluster[/blue]")

        try:
            cluster_response = self.eks.describe_cluster(name=cluster_name)
            access_config = cluster_response['cluster'].get('accessConfig', {})
            authentication_mode = access_config.get('authenticationMode')

            if authentication_mode in ['API', 'API_AND_CONFIG_MAP']:
                try:
                    self.eks.delete_access_entry(
                        clusterName=cluster_name,
                        principalArn=node_role_arn
                    )
                    console.print("[green]✅ Access entry deleted[/green]")
                    return
                except self.eks.exceptions.ResourceNotFoundException:
                    pass
        except Exception as e:
            console.print(
                f"[yellow]Could not delete Access entry from cluster{e}[/yellow]")
