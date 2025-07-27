"""List clusters command for showing onboarded clusters."""

import typer
from typing import Optional
from rich.console import Console
from rich.table import Table
from rich.prompt import Prompt

from source.aws.ssm import SSMClient

console = Console()


def list_clusters_command(
    region: Optional[str] = typer.Option(None, "--region", "-r", help="AWS region"),
):
    """List onboarded clusters."""
    
    console.print("[bold blue]📋 Onboarded Clusters[/bold blue]")

    if not region:
        region = Prompt.ask("AWS Region")
        
    ssm_client = SSMClient(region)
    clusters = ssm_client.list_onboarded_clusters()

    if not clusters:
        console.print("[yellow]No clusters onboarded yet[/yellow]")
        console.print("[blue]Run: [cyan]spotter onboard <cluster-name>[/cyan][/blue]")
        return

    table = Table()
    table.add_column("Cluster", style="cyan")
    table.add_column("Region", style="green")
    table.add_column("Launch Template", style="yellow")
    table.add_column("Subnets", style="magenta")

    for cluster in clusters:
        template_id = cluster['launch_template_id']
        if len(template_id) > 20:
            template_id = template_id[:20] + '...'

        table.add_row(
            cluster['name'],
            cluster['region'],
            template_id,
            f"{cluster['subnet_count']} subnets"
        )

    console.print(table)
