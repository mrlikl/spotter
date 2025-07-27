"""Rebalance command for redistributing instances across AZs."""

import typer
from typing import Optional, Dict, List
from rich.console import Console
from rich.table import Table
from rich.prompt import Confirm, Prompt
from collections import Counter

from source.aws.ssm import SSMClient
from source.aws.ec2 import EC2Client
from source.aws.lambda_client import LambdaClient

console = Console()


def rebalance_command(
    cluster: str = typer.Argument(..., help="EKS cluster name"),
    region: Optional[str] = typer.Option(None, "--region", "-r", help="AWS region"),
):
    """Rebalance instances across availability zones."""
    
    console.print(f"[bold blue]⚖️ Rebalancing {cluster}[/bold blue]")
    
    try:
        if not region:
            region = Prompt.ask("AWS Region")
        
        ssm_client = SSMClient(region)
        settings = ssm_client.get_cluster_settings(cluster)
        if not settings:
            console.print(f"[red]Cluster {cluster} not onboarded[/red]")
            raise typer.Exit(1)
        
        available_azs = list(settings.get('subnet_map', {}).keys())
        if not available_azs:
            console.print("[red]No availability zones found in cluster settings[/red]")
            raise typer.Exit(1)
        
        console.print(f"[blue]Available AZs: {', '.join(available_azs)}[/blue]")
        
        ec2_client = EC2Client(region)
        current_instances = ec2_client.get_spotter_instances(cluster)
        
        if not current_instances:
            console.print("[yellow]No instances found[/yellow]")
            return
        
        az_distribution = _analyze_distribution(current_instances, available_azs)
        rebalance_plan = _create_rebalance_plan(az_distribution, available_azs)
        
        if not rebalance_plan['needed']:
            console.print("[green]✅ Instances already balanced[/green]")
            return
        
        _display_rebalance_plan(az_distribution, rebalance_plan, available_azs)
        
        if not Confirm.ask("Proceed with rebalancing?"):
            console.print("[yellow]Cancelled[/yellow]")
            return
        
        lambda_client = LambdaClient(region)
        _execute_rebalance(rebalance_plan, cluster, lambda_client, ec2_client)
        
        console.print("[green]✅ Rebalancing completed[/green]")
        
    except Exception as e:
        console.print(f"[red]Rebalancing failed: {e}[/red]")
        raise typer.Exit(1)


def _analyze_distribution(instances: List[Dict], available_azs: List[str]) -> Dict:
    """Analyze current AZ distribution against all available AZs."""
    az_counts = Counter(instance['availability_zone'] for instance in instances)
    
    distribution_by_az = {}
    for az in available_azs:
        distribution_by_az[az] = az_counts.get(az, 0)
    
    return {
        'total': len(instances),
        'by_az': distribution_by_az,
        'instances': instances
    }


def _create_rebalance_plan(distribution: Dict, available_azs: List[str]) -> Dict:
    """Create rebalancing plan based on all available AZs."""
    total_instances = distribution['total']
    az_counts = distribution['by_az']
    
    if len(available_azs) <= 1:
        return {'needed': False, 'reason': 'Only one AZ available'}
    
    ideal_per_az = total_instances // len(available_azs)
    extra_instances = total_instances % len(available_azs)
    
    moves = []
    heavy_azs = []
    light_azs = []
    
    for i, az in enumerate(available_azs):
        current_count = az_counts.get(az, 0)
        target_count = ideal_per_az + (1 if i < extra_instances else 0)
        
        if current_count > target_count:
            excess = current_count - target_count
            heavy_azs.append({'az': az, 'excess': excess, 'current': current_count, 'target': target_count})
        elif current_count < target_count:
            deficit = target_count - current_count
            light_azs.append({'az': az, 'deficit': deficit, 'current': current_count, 'target': target_count})
    
    for heavy in heavy_azs:
        for light in light_azs:
            if heavy['excess'] > 0 and light['deficit'] > 0:
                move_count = min(heavy['excess'], light['deficit'])
                moves.append({
                    'from_az': heavy['az'],
                    'to_az': light['az'],
                    'count': move_count
                })
                heavy['excess'] -= move_count
                light['deficit'] -= move_count
    
    return {
        'needed': len(moves) > 0,
        'moves': moves,
        'heavy_azs': heavy_azs,
        'light_azs': light_azs,
        'ideal_per_az': ideal_per_az,
        'extra_instances': extra_instances
    }


def _display_rebalance_plan(distribution: Dict, plan: Dict, available_azs: List[str]):
    """Display current distribution and rebalancing plan."""
    
    console.print("\n[bold]Current Distribution:[/bold]")
    table = Table()
    table.add_column("AZ", style="cyan")
    table.add_column("Current", style="green", justify="right")
    table.add_column("Target", style="blue", justify="right")
    table.add_column("Status", style="yellow")
    
    for az in available_azs:
        current_count = distribution['by_az'].get(az, 0)
        az_index = available_azs.index(az)
        target_count = plan['ideal_per_az'] + (1 if az_index < plan['extra_instances'] else 0)
        
        if current_count > target_count:
            status = "[red]Heavy[/red]"
        elif current_count < target_count:
            status = "[yellow]Light[/yellow]"
        else:
            status = "[green]Balanced[/green]"
        
        table.add_row(az, str(current_count), str(target_count), status)
    
    console.print(table)
    
    if plan['moves']:
        console.print("\n[bold]Rebalancing Plan:[/bold]")
        for move in plan['moves']:
            console.print(f"• Move {move['count']} instance(s) from [red]{move['from_az']}[/red] to [green]{move['to_az']}[/green]")


def _execute_rebalance(plan: Dict, cluster_name: str, lambda_client: LambdaClient, ec2_client: EC2Client):
    """Execute the rebalancing plan."""
    
    for move in plan['moves']:
        from_az = move['from_az']
        to_az = move['to_az']
        count = move['count']
        
        console.print(f"[blue]Moving {count} instance(s) from {from_az} to {to_az}[/blue]")
        
        instances_to_terminate = ec2_client.get_instances_in_az(cluster_name, from_az, count)
        
        if len(instances_to_terminate) < count:
            console.print(f"[yellow]Warning: Only found {len(instances_to_terminate)} instances in {from_az}[/yellow]")
        
        try:
            lambda_client.invoke_lambda('InstanceRunner', {
                'cluster': cluster_name,
                'count': len(instances_to_terminate),
                'az': to_az
            })
            
            console.print(f"[green]✅ Launched {len(instances_to_terminate)} instance(s) in {to_az}[/green]")
            
        except Exception as e:
            console.print(f"[red]Failed to launch instances in {to_az}: {e}[/red]")
            continue
        
        if instances_to_terminate:
            try:
                ec2_client.terminate_instances_by_ids([inst['instance_id'] for inst in instances_to_terminate])
                console.print(f"[green]✅ Terminated {len(instances_to_terminate)} instance(s) in {from_az}[/green]")
            except Exception as e:
                console.print(f"[red]Failed to terminate instances in {from_az}: {e}[/red]")
