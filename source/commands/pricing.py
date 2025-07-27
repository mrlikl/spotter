"""Pricing command for visualizing spot price data."""

import typer
import json
from typing import Optional, List, Dict
from rich.console import Console
from rich.table import Table
from rich.panel import Panel
from rich.columns import Columns
from rich.prompt import Prompt
from rich.progress import Progress, SpinnerColumn, TextColumn

from source.aws.ssm import SSMClient

console = Console()


def pricing_command(
    region: Optional[str] = typer.Option(None, "--region", "-r", help="AWS region"),
):
    """Display spot pricing dashboard."""

    console.print("[bold blue]💰 Pricing Dashboard[/bold blue]")

    if not region:
        region = Prompt.ask("AWS Region")

    pricing_data = _get_pricing_data(region)
    if not pricing_data:
        console.print(f"[yellow]No pricing data found[/yellow]")
        console.print(f"[blue]Run: [cyan]spotter refresh --region {region}[/cyan][/blue]")
        return

    _display_pricing_dashboard(pricing_data)


def _get_pricing_data(region: str) -> Dict[str, List[Dict]]:
    """Get pricing data from SSM parameters."""

    with Progress(
        SpinnerColumn(),
        TextColumn("[progress.description]{task.description}"),
        console=console,
    ) as progress:
        task = progress.add_task("Loading pricing data...", total=None)

        ssm_client = SSMClient(region)
        pricing_data = {}

        try:
            response = ssm_client.get_parameters_by_path("/spotter/prices/")

            for param in response:
                az_name = param['Name'].split('/')[-1]
                try:
                    data = json.loads(param['Value'])
                    pricing_data[az_name] = data
                except json.JSONDecodeError:
                    continue

            progress.update(task, description="Pricing data loaded")
            return pricing_data

        except Exception as e:
            console.print(f"[red]Failed to load pricing data: {e}[/red]")
            return {}


def _display_pricing_dashboard(pricing_data: Dict[str, List[Dict]]):
    """Display pricing dashboard with tables for each AZ."""

    if not pricing_data:
        return

    panels = []

    for az, instances in pricing_data.items():
        sorted_instances = sorted(instances, key=lambda x: x['spot_price'])

        table = Table(show_header=True, header_style="bold magenta")
        table.add_column("Instance Type", style="cyan", width=15)
        table.add_column("Spot Price", style="green", justify="right", width=12)

        for instance in sorted_instances:
            table.add_row(
                instance['instance_type'],
                f"${instance['spot_price']:.4f}"
            )

        panel = Panel(
            table,
            title=f"[bold blue]{az}[/bold blue]",
            title_align="left",
            border_style="blue"
        )
        panels.append(panel)

    if len(panels) <= 2:
        console.print(Columns(panels))
    else:
        for i in range(0, len(panels), 2):
            row_panels = panels[i:i+2]
            console.print(Columns(row_panels))
            if i + 2 < len(panels):
                console.print()

    console.print(f"\n[bold]Summary:[/bold] {len(pricing_data)} availability zones")

    all_instances = []
    for az, instances in pricing_data.items():
        for instance in instances:
            all_instances.append({**instance, 'az': az})

    if all_instances:
        cheapest = min(all_instances, key=lambda x: x['spot_price'])
        console.print(f"[green]Cheapest: {cheapest['instance_type']} in {cheapest['az']} at ${cheapest['spot_price']:.4f}[/green]")
