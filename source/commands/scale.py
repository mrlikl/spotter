"""Scale command for launching and terminating Spotter instances."""

import typer
import json
from typing import Optional
from rich.console import Console
from rich.table import Table
from rich.progress import Progress, SpinnerColumn, TextColumn
from rich.prompt import Prompt

from source.aws.ssm import SSMClient
from source.aws.ec2 import EC2Client
from source.aws.lambda_client import LambdaClient

console = Console()


def scale_command(
    cluster: str = typer.Argument(..., help="EKS cluster name"),
    count: int = typer.Option(..., "--count", help="Number of spot instances"),
    scale_to_count: bool = typer.Option(False, "--scale-to-count", help="Scale up or down to match the count"),
    region: Optional[str] = typer.Option(None, "--region", "-r", help="AWS region"),
):
    """Scale Spotter instances for a cluster up or down."""
    
    console.print(f"[bold blue]📉 Scaling {cluster}[/bold blue]")    
    
    try:
        if not region:
            region = Prompt.ask("AWS Region")
        
        ssm_client = SSMClient(region)
        settings = ssm_client.get_cluster_settings(cluster)
        if not settings:
            console.print(f"[red]Cluster {cluster} not onboarded[/red]")
            raise typer.Exit(1)

        ec2_client = EC2Client(region)
        lambda_client = LambdaClient(region)
        
        if scale_to_count:
            current_instances = ec2_client.get_spotter_instances(cluster)
            current_count = len(current_instances)
            
            console.print(f"[blue]Current: {current_count} | Target: {count}[/blue]")
            
            if current_count < count:
                launch_count = count - current_count
                console.print(f"[green]Scaling up {launch_count} instances[/green]")
                _launch_instances(lambda_client, cluster, launch_count)
            elif current_count > count:
                excess_count = current_count - count
                console.print(f"[red]Scaling down {excess_count} instances[/red]")
                instances_to_terminate = current_instances[:excess_count]
                success = ec2_client.terminate_instances(instances_to_terminate)
                if not success:
                    return
                
                console.print(f"[blue]Remaining: {count} instances[/blue]")
            else:
                console.print("[green]Already at target count[/green]")
        else:
            _launch_instances(lambda_client, cluster, count)
            
    except Exception as e:
        console.print(f"[red]Scaling failed: {e}[/red]")
        raise typer.Exit(1)


def _launch_instances(lambda_client: LambdaClient, cluster_name: str, launch_count: int):
    """Launch instances by invoking InstanceRunner Lambda."""
    
    if launch_count <= 0:
        return
    
    payload = {
        'cluster': cluster_name,
        'count': launch_count
    }
    
    try:
        with Progress(
            SpinnerColumn(),
            TextColumn("[progress.description]{task.description}"),
            console=console,
        ) as progress:
            task = progress.add_task(f"Launching {launch_count} instances...", total=None)
            
            response = lambda_client.invoke_lambda(
                function_name='InstanceRunner',
                payload=payload
            )
            
            progress.update(task, description="Lambda invocation completed")
        
        response_payload = json.loads(response['Payload'].read())
        
        if response['StatusCode'] == 200:
            body = json.loads(response_payload['body'])
            launched_count = body.get('total_launched', 0)
            launched_instances = body.get('launched_instances', [])
            
            console.print(f"[green]✅ Launched {launched_count} instances[/green]")
            
            if launched_instances:
                table = Table()
                table.add_column("Instance ID", style="cyan")
                table.add_column("Type", style="green")
                table.add_column("AZ", style="yellow")
                table.add_column("Retry", style="magenta")
                
                for instance in launched_instances:
                    table.add_row(
                        instance['instance_id'],
                        instance['instance_type'],
                        instance['az'],
                        str(instance.get('retry_count', 0))
                    )
                
                console.print(table)
        else:
            error_body = json.loads(response_payload['body'])
            error_msg = error_body.get('error', 'Unknown error')
            console.print(f"[red]Lambda invocation failed: {error_msg}[/red]")
            raise Exception(f"Lambda failed: {error_msg}")
            
    except Exception as e:
        console.print(f"[red]Failed to launch instances: {e}[/red]")
        raise
