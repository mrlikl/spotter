"""Offboard command for removing clusters from Spotter."""

import typer
from typing import Optional
from rich.console import Console
from rich.prompt import Prompt, Confirm

from source.aws.ssm import SSMClient
from source.aws.ec2 import EC2Client
from source.aws.cloudformation import CloudFormationClient
from source.aws.eks import EKSClient

console = Console()


def offboard_command(
    cluster_name: str = typer.Argument(..., help="EKS cluster name to remove"),
    region: Optional[str] = typer.Option(None, "--region", "-r", help="AWS region")
):
    """Remove a cluster from Spotter."""

    if not region:
        region = Prompt.ask("AWS Region")

    console.print(f"[red]⚠️  Remove cluster {cluster_name} from Spotter?[/red]")
    console.print("• Delete SSM settings")
    console.print("• Delete CloudFormation stack")
    console.print("• Terminate running instances")

    if not Confirm.ask("Are you sure?"):
        console.print("[yellow]Cancelled[/yellow]")
        raise typer.Exit()

    console.print(f"[red]Removing {cluster_name}...[/red]")

    ssm_client = SSMClient(region) 
    ec2_client = EC2Client(region)
    cfn_client = CloudFormationClient(region)
    eks_client = EKSClient(region)

    ec2_client.terminate_cluster_instances(cluster_name)

    stack_name = f"SpotterNodeResources-{cluster_name}"
    
    node_role_arn = cfn_client.get_stack_output(stack_name, 'NodeInstanceRole')
    if node_role_arn:
        eks_client.delete_access_entry(cluster_name, node_role_arn)
    
    console.print(f"[blue]Deleting stack {stack_name}...[/blue]")

    try:
        success = cfn_client.delete_stack(stack_name)
        if success:
            console.print("[green]✅ Stack deletion completed[/green]")
        else:
            console.print(f"[yellow]Manual cleanup: [cyan]aws cloudformation delete-stack --stack-name {stack_name}[/cyan][/yellow]")
    except Exception as e:
        console.print(f"[yellow]Stack deletion failed: {e}[/yellow]")
        console.print(f"[cyan]aws cloudformation delete-stack --stack-name {stack_name}[/cyan]")

    ssm_client.delete_cluster_settings(cluster_name)
    console.print(f"[green]✅ {cluster_name} removed[/green]")
