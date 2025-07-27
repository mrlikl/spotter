"""List instances command for showing current instance status."""

import typer
from typing import Optional
from rich.console import Console
from rich.table import Table
from rich.prompt import Prompt

from source.aws.ssm import SSMClient
from source.aws.ec2 import EC2Client

console = Console()


def list_instances_command(
    cluster: str = typer.Argument(..., help="EKS cluster name"),
    region: Optional[str] = typer.Option(None, "--region", "-r", help="AWS region"),
):
    """Show current instance status for a cluster."""
    
    console.print(f"[bold blue]📊 {cluster} Instances[/bold blue]")
    
    try:
        if not region:
            region = Prompt.ask("AWS Region")
            
        ssm_client = SSMClient(region)
        settings = ssm_client.get_cluster_settings(cluster)
        if not settings:
            console.print(f"[red]Cluster {cluster} not onboarded[/red]")
            raise typer.Exit(1)

        ec2_client = EC2Client(region)
        instances = ec2_client.get_spotter_instances(cluster)
        
        if not instances:
            console.print("[yellow]No instances found[/yellow]")
            return
        
        console.print(f"[green]Total: {len(instances)} instances[/green]")
        
        # AZ distribution
        az_groups = {}
        for instance in instances:
            az = instance['availability_zone']
            az_groups[az] = az_groups.get(az, 0) + 1
        
        console.print(f"[blue]Distribution: {', '.join(f'{az}({count})' for az, count in sorted(az_groups.items()))}[/blue]")
        
        # Instance table
        table = Table()
        table.add_column("Instance ID", style="cyan")
        table.add_column("Type", style="green")
        table.add_column("AZ", style="yellow")
        table.add_column("State", style="magenta")
        table.add_column("Launch Time", style="blue")
        
        for instance in instances:
            table.add_row(
                instance['instance_id'],
                instance['instance_type'],
                instance['availability_zone'],
                instance['state'],
                instance['launch_time'].strftime('%m-%d %H:%M')
            )
        
        console.print(table)
        
    except Exception as e:
        console.print(f"[red]Failed: {e}[/red]")
        raise typer.Exit(1)
