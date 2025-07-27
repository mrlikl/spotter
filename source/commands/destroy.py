"""Destroy command for Spotter infrastructure removal."""

import typer
from typing import Optional
from rich.console import Console
from rich.prompt import Prompt, Confirm

from source.aws.sam import SAMDeployer
from source.aws.ssm import SSMClient

console = Console()


def destroy_command(
    region: Optional[str] = typer.Option(None, "--region", "-r", help="AWS region")
):
    """Destroy Spotter infrastructure."""

    if not region:
        region = Prompt.ask("AWS Region")

    console.print("[red]⚠️  This will destroy all Spotter infrastructure![/red]")
    console.print("• Delete Spotter CloudFormation stack")
    console.print("• Delete pricing data (/spotter/prices/*)")
    console.print("• All onboarded clusters will stop working")

    if not Confirm.ask("Are you sure?"):
        console.print("[yellow]Destruction cancelled[/yellow]")
        raise typer.Exit()

    console.print("[red]Destroying Spotter stack...[/red]")
    sam_deployer = SAMDeployer()
    success = sam_deployer.delete_stack('Spotter', region)
    
    if success:
        console.print("[green]✅ Spotter stack destroyed[/green]")
    else:
        console.print("[yellow]Stack deletion failed - cleanup manually[/yellow]")

    ssm_client = SSMClient(region)
    ssm_client.cleanup_pricing_parameters()

    console.print("[blue]To remove clusters: [cyan]spotter offboard <cluster-name>[/cyan][/blue]")
