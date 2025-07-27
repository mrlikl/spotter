"""Refresh command for manually triggering spot price analysis."""

import typer
from typing import Optional
from rich.console import Console
from rich.prompt import Prompt

from source.aws.lambda_client import LambdaClient

console = Console()


def refresh_prices_command(
    region: Optional[str] = typer.Option(None, "--region", "-r", help="AWS region"),
):
    """Refresh spot pricing data by invoking the Spotter Lambda function."""

    console.print("[bold blue]🔄 Refreshing Spot Prices[/bold blue]")

    if not region:
        region = Prompt.ask("AWS Region")

    console.print(f"[blue]Invoking Spotter Lambda in {region}[/blue]")

    lambda_client = LambdaClient(region)
    success = _invoke_spotter_lambda(lambda_client)
    if not success:
        raise typer.Exit(1)

    console.print("[green]✅ Spot price refresh completed[/green]")
    console.print("[blue]Pricing data updated in SSM: [cyan]/spotter/prices/{az}[/cyan][/blue]")


def _invoke_spotter_lambda(lambda_client: LambdaClient) -> bool:
    """Invoke the Spotter Lambda function."""
    
    try:
        response = lambda_client.invoke_lambda_sync('Spotter')
        
        if response['success']:
            console.print("[green]Lambda execution successful[/green]")
            return True
        else:
            console.print(f"[red]Lambda invocation failed: {response.get('error', 'Unknown error')}[/red]")
            return False

    except Exception as e:
        if "ResourceNotFoundException" in str(e):
            console.print("[red]❌ Spotter Lambda function not found[/red]")
            console.print("[yellow]Run [cyan]spotter bootstrap[/cyan] first[/yellow]")
        else:
            console.print(f"[red]❌ Failed to invoke Spotter Lambda: {e}[/red]")
        return False
