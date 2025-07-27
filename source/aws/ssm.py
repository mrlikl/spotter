"""AWS SSM client utilities."""

import boto3
import json
from typing import List, Dict, Optional
from rich.console import Console

console = Console()


class SSMClient:
    """AWS SSM client wrapper."""

    def __init__(self, region: str):
        self.region = region
        self.ssm = boto3.client('ssm', region_name=region)

    def get_parameters_by_path(self, path: str) -> Optional[Dict]:
        try:
            response = self.ssm.get_parameters_by_path(
                Path=path,
                Recursive=True
            )
            return response.get('Parameters', [])
        except Exception as e:
            console.print(f"[red]Failed to get SSM parameters: {e}[/red]")
            return None

    def cleanup_pricing_parameters(self) -> bool:
        """Clean up /spotter/prices/* SSM parameters."""
        console.print("[blue]Cleaning up Spotter pricing parameters...[/blue]")

        try:
            
            parameters = self.get_parameters_by_path("/spotter/prices/")

            if not parameters:
                console.print(
                    "[green]✅ No pricing parameters found to clean up[/green]")
                return True

            console.print(
                f"[yellow]Found {len(parameters)} pricing parameters to delete[/yellow]")

            param_names = [param['Name'] for param in parameters]

            try:
                self.ssm.delete_parameters(Names=param_names)
                console.print(
                    f"[green]✅ Cleaned up pricing parameters[/green]")
                return True
            except Exception as e:
                console.print(
                    f"[yellow]Failed to delete some parameters: {e}[/yellow]")
                return False

        except Exception as e:
            console.print(
                f"[yellow]Failed to clean up pricing parameters: {e}[/yellow]")
            return False

    def create_cluster_settings(self, cluster_name: str, settings: Dict) -> bool:
        """Create SSM parameter with cluster settings."""
        console.print(f"[blue]Saving cluster settings...[/blue]")

        param_name = f"/spotter/settings/{cluster_name}"

        try:
            self.ssm.put_parameter(
                Name=param_name,
                Value=json.dumps(settings),
                Type='String',
                Overwrite=True,
                Description=f"Spotter settings for EKS cluster {cluster_name}",
            )
            self.ssm.add_tags_to_resource(
                ResourceType='Parameter',
                ResourceId=param_name,
                Tags=[
                    {
                        'Key': 'managedby',
                        'Value': 'spotter'
                    },
                ]
            )
            return True
        except Exception as e:
            console.print(f"[red]Failed to create SSM parameter: {e}[/red]")
            return False

    def get_cluster_settings(self, cluster_name: str) -> Optional[Dict]:
        """Get cluster settings from SSM parameter."""
        param_name = f"/spotter/settings/{cluster_name}"

        try:
            response = self.ssm.get_parameter(Name=param_name)
            return json.loads(response['Parameter']['Value'])
        except Exception:
            return None

    def delete_cluster_settings(self, cluster_name: str) -> bool:
        """Delete cluster settings SSM parameter."""
        param_name = f"/spotter/settings/{cluster_name}"

        try:
            self.ssm.delete_parameter(Name=param_name)
            console.print(
                f"[green]✅ Deleted SSM parameter: {param_name}[/green]")
            return True
        except Exception as e:
            console.print(
                f"[yellow]Could not delete SSM parameter: {e}[/yellow]")
            return False

    def list_onboarded_clusters(self) -> List[Dict]:
        """List all onboarded clusters."""
        try:
            response = self.ssm.get_parameters_by_path(
                Path="/spotter/settings/",
                Recursive=True
            )

            clusters = []
            for param in response['Parameters']:
                cluster_name = param['Name'].split('/')[-1]
                try:
                    settings = json.loads(param['Value'])
                    clusters.append({
                        'name': cluster_name,
                        'region': settings.get('region', 'N/A'),
                        'launch_template_id': settings.get('launch_template_id', 'N/A'),
                        'subnet_count': len(settings.get('subnet_map', {}))
                    })
                except json.JSONDecodeError:
                    clusters.append({
                        'name': cluster_name,
                        'region': 'Error',
                        'launch_template_id': 'Error',
                        'subnet_count': 0
                    })

            return clusters

        except Exception as e:
            console.print(f"[red]Failed to list onboarded clusters: {e}[/red]")
            return []
