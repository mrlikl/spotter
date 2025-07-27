"""Onboard command for cluster-specific Spotter setup."""

import typer
from pathlib import Path
from typing import Optional
from rich.console import Console
from rich.table import Table
from rich.prompt import Prompt

from source.aws.eks import EKSClient
from source.aws.ec2 import EC2Client
from source.aws.cloudformation import CloudFormationClient
from source.aws.ssm import SSMClient

console = Console()


def onboard_command(
    cluster_name: str = typer.Argument(..., help="EKS cluster name to onboard"),
    region: Optional[str] = typer.Option(None, "--region", "-r", help="AWS region"),
    subnet_ids: Optional[str] = typer.Option(None, "--subnets", "-s", help="Comma-separated subnet IDs to launch worker nodes"),
):
    """Onboard an EKS cluster to Spotter."""

    console.print(f"[bold blue]🚀 Onboarding {cluster_name}[/bold blue]")

    params = _get_onboard_parameters(cluster_name, region, subnet_ids)
    if not params:
        raise typer.Exit(1)

    cfn_client = CloudFormationClient(params['region'])
    template_path = Path(__file__).parent.parent / "cloudformation" / "launch-template.yml"
    
    if not template_path.exists():
        console.print(f"[red]Template not found: {template_path}[/red]")
        return False
        
    success = cfn_client.deploy_stack(
        stack_name=params['stack_name'],
        template_path=str(template_path),
        parameters={
            'ClusterSecurityGroup': params['cluster_sg'],
            'ClusterVersion': params['version'],
            'ClusterCA': params['ca_data'],
            'ClusterName': params['cluster_name'],
            'ClusterEndpoint': params['endpoint'],
            'ServiceCIDR': params['service_cidr']
        },
        capabilities=['CAPABILITY_NAMED_IAM'],
        tags={'managedby': 'spotter', 'cluster': params['cluster_name']}
    )
    
    if not success:
        raise typer.Exit(1)

    launch_template_id = cfn_client.get_stack_output(params['stack_name'], 'LaunchTemplateId')
    if not launch_template_id:
        console.print("[red]Could not retrieve launch template ID[/red]")
        raise typer.Exit(1)

    node_role_arn = cfn_client.get_stack_output(params['stack_name'], 'NodeInstanceRole')
    if node_role_arn:
        eks_client = EKSClient(params['region'])
        eks_client.handle_access_entry(params['cluster_name'], node_role_arn)

    settings = {
        'cluster_name': params['cluster_name'],
        'launch_template_id': launch_template_id,
        'subnet_ids': params['subnet_ids'],
        'subnet_map': params['subnet_map'],
        'region': params['region'],
    }

    ssm_client = SSMClient(params['region'])
    success = ssm_client.create_cluster_settings(params['cluster_name'], settings)
    if not success:
        raise typer.Exit(1)

    console.print(f"[green]✅ {cluster_name} onboarded[/green]")
    console.print(f"[blue]Next: [cyan]spotter scale {cluster_name} --count 2[/cyan][/blue]")


def _get_onboard_parameters(cluster_name: str, region: Optional[str], subnet_ids: Optional[str]) -> Optional[dict]:
    """Get onboarding parameters from CLI args or user input."""

    if not region:
        region = Prompt.ask("AWS Region")

    try:
        eks_client = EKSClient(region)
        ec2_client = EC2Client(region)
        cluster_details = eks_client.get_cluster_details(cluster_name)
    except Exception as e:
        console.print(f"[red]Failed to get cluster details: {e}[/red]")
        return None

    if not subnet_ids:
        try:
            subnets = ec2_client.list_vpc_subnets(cluster_details['vpc_id'])

            console.print(f"[blue]Subnets in VPC {cluster_details['vpc_id']}:[/blue]")
            table = Table()
            table.add_column("Subnet ID", style="cyan")
            table.add_column("AZ", style="green")
            table.add_column("CIDR", style="yellow")
            table.add_column("Name", style="magenta")

            for subnet in subnets:
                table.add_row(
                    subnet['subnet_id'],
                    subnet['availability_zone'],
                    subnet['cidr_block'],
                    subnet.get('name', '')
                )

            console.print(table)
            subnet_ids = Prompt.ask("Subnet IDs to launch worker nodes(comma-separated)")
            
        except Exception as e:
            console.print(f"[red]Failed to list subnets: {e}[/red]")
            return None

    subnet_list = [s.strip() for s in subnet_ids.split(',')]
    subnet_map = {}
    
    try:
        subnets = ec2_client.list_vpc_subnets(cluster_details['vpc_id'])
        for subnet in subnets:
            if subnet['subnet_id'] in subnet_list:
                subnet_map[subnet['availability_zone']] = subnet['subnet_id']
    except Exception as e:
        console.print(f"[red]Failed to list subnets: {e}[/red]")
        return None

    return {
        'cluster_name': cluster_name,
        'region': region,
        'subnet_ids': subnet_ids,
        'subnet_map': subnet_map,
        'stack_name': f'SpotterNodeResources-{cluster_name}',
        **cluster_details
    }
