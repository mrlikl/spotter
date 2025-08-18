"""Main CLI application for Spotter."""

import typer
from rich.console import Console
from rich.traceback import install
from importlib.metadata import version
from source.commands.bootstrap import bootstrap_command
from source.commands.destroy import destroy_command
from source.commands.onboard import onboard_command
from source.commands.list_clusters import list_clusters_command
from source.commands.offboard import offboard_command
from source.commands.scale import scale_command
from source.commands.list_instances import list_instances_command
from source.commands.refresh import refresh_prices_command
from source.commands.pricing import pricing_command
from source.commands.rebalance import rebalance_command

install(show_locals=True)

console = Console()


def version_callback():
    pkg_version = version("spotter-cli")
    console.print(f"[bold blue]Spotter[/bold blue] version [green]{pkg_version}[/green]")
    raise typer.Exit()


app = typer.Typer(
    name="spotter",
    help="Production-grade spot instance scheduling for EKS worker nodes",
    rich_markup_mode="rich",
    no_args_is_help=False,
    add_completion=False,
)


@app.callback(invoke_without_command=True)
def main(
    ctx: typer.Context,
    version: bool = typer.Option(False, "--version", "-v", callback=version_callback, help="Show version and exit")
):
    """Production-grade spot instance scheduling for EKS worker nodes"""
    if ctx.invoked_subcommand is None:
        console.print(ctx.get_help())
        raise typer.Exit()


app.command("bootstrap", help="Deploy Spotter infrastructure")(bootstrap_command)
app.command("destroy", help="Destroy Spotter infrastructure")(destroy_command)
app.command("onboard", help="Onboard an EKS cluster to Spotter")(onboard_command)
app.command("list-clusters", help="List onboarded clusters")(list_clusters_command)
app.command("offboard", help="Remove a cluster from Spotter")(offboard_command)
app.command("scale", help="Scale Spotter instances for a cluster")(scale_command)
app.command("list-instances", help="Show current instance status for a cluster")(list_instances_command)
app.command("rebalance", help="Rebalance instances across availability zones")(rebalance_command)
app.command("refresh-prices", help="Refresh spot pricing data")(refresh_prices_command)
app.command("pricing", help="View spot pricing data")(pricing_command)


if __name__ == "__main__":
    app()
