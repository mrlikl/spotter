"""AWS Lambda client utilities."""

import boto3
import json
import base64
from typing import Dict
from rich.console import Console
from rich.progress import Progress, SpinnerColumn, TextColumn

console = Console()


class LambdaClient:
    """AWS Lambda client wrapper."""
    
    def __init__(self, region: str):
        self.region = region
        self.lambda_client = boto3.client('lambda', region_name=region)
    
    def invoke_lambda(self, function_name: str, payload: Dict) -> Dict:
        """Invoke a Lambda function with the given payload."""
        return self.lambda_client.invoke(
            FunctionName=function_name,
            InvocationType='RequestResponse',
            Payload=json.dumps(payload)
        )
    
    def invoke_lambda_sync(self, function_name: str, payload: Dict = None) -> Dict:
        """Invoke a Lambda function synchronously with progress display."""
        try:
            with Progress(
                SpinnerColumn(),
                TextColumn("[progress.description]{task.description}"),
                console=console,
            ) as progress:
                task = progress.add_task("Analyzing spot prices...", total=None)

                # Handle None payload - don't pass Payload parameter if None
                if payload:
                    response = self.lambda_client.invoke(
                        FunctionName=function_name,
                        InvocationType='RequestResponse',
                        Payload=json.dumps(payload)
                    )
                else:
                    response = self.lambda_client.invoke(
                        FunctionName=function_name,
                        InvocationType='RequestResponse'
                    )

                progress.update(task, description="Spot price analysis completed")

            if response['StatusCode'] == 200:
                payload_data = response.get('Payload')
                if payload_data:
                    result = json.loads(payload_data.read())

                if 'LogResult' in response:
                    logs = base64.b64decode(response['LogResult']).decode('utf-8')
                    if logs.strip():
                        console.print(f"[yellow]Lambda logs:[/yellow]")
                        console.print(f"[dim]{logs}[/dim]")

                return {'success': True, 'response': response}
            else:
                return {
                    'success': False, 
                    'error': f"Lambda invocation failed with status code: {response['StatusCode']}"
                }

        except self.lambda_client.exceptions.ResourceNotFoundException:
            return {'success': False, 'error': 'Lambda function not found'}
        except Exception as e:
            return {'success': False, 'error': str(e)}
