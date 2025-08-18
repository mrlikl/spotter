"""Bootstrap command for Spotter infrastructure deployment."""

import typer
from pathlib import Path
from typing import Optional
from rich.console import Console
from rich.prompt import Prompt

from source.aws.sam import SAMDeployer

console = Console()


def bootstrap_command(
    region: Optional[str] = typer.Option(None, "--region", "-r", help="AWS region"),
    min_savings_percent: int = typer.Option(70, "--min-savings", help="Minimum savings percentage"),
    check_frequency_minutes: int = typer.Option(10, "--check-frequency", help="Check frequency in minutes"),
):
    """Deploy Spotter infrastructure."""

    console.print("[bold blue]🚀 Bootstrapping Spotter[/bold blue]")

    if not region:
        region = Prompt.ask("AWS Region")

    if min_savings_percent < 0 or min_savings_percent > 100:
        console.print("[red]Min savings percent must be between 0 and 100[/red]")
        raise typer.Exit(1)

    if check_frequency_minutes < 1 or check_frequency_minutes > 1440:
        console.print("[red]Check frequency must be between 1 and 1440 minutes[/red]")
        raise typer.Exit(1)

    console.print(f"[blue]Region: [cyan]{region}[/cyan] | Min Savings: [cyan]{min_savings_percent}%[/cyan] | Frequency: [cyan]{check_frequency_minutes}min[/cyan][/blue]")

    sam_deployer = SAMDeployer()
    template_path = Path(__file__).parent.parent / "cloudformation" / "template.yml"
    
    success = sam_deployer.deploy(
        stack_name='Spotter',
        region=region,
        template_path=str(template_path),
        parameters={
            'MinSavingsPercent': str(min_savings_percent),
            'CheckFrequencyMinutes': str(check_frequency_minutes)
        },
        capabilities=['CAPABILITY_IAM'],
        confirm_changeset=False,
        tags={'managedby': 'spotter'}
    )
    
    if not success:
        raise typer.Exit(1)

    console.print(f"[green]✅ Spotter bootstrapped in {region}[/green]")
    console.print("[blue]Next: [cyan]spotter onboard <cluster-name>[/cyan][/blue]")
