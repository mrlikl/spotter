"""AWS CloudFormation client utilities."""

import boto3
from typing import Dict, Optional
from botocore.exceptions import ClientError
from rich.console import Console
from rich.progress import Progress, SpinnerColumn, TextColumn

console = Console()


class CloudFormationClient:
    """AWS CloudFormation client wrapper."""

    def __init__(self, region: str):
        self.region = region
        self.cfn = boto3.client('cloudformation', region_name=region)

    def deploy_stack(
        self,
        stack_name: str,
        template_path: str,
        parameters: Dict[str, str],
        capabilities: Optional[list] = None,
        tags: Optional[Dict[str, str]] = None
    ) -> bool:
        """Deploy CloudFormation stack."""
        try:
            with open(template_path, 'r') as f:
                template_body = f.read()

            cfn_parameters = [
                {'ParameterKey': k, 'ParameterValue': v}
                for k, v in parameters.items()
            ]

            cfn_tags = [
                {'Key': k, 'Value': v}
                for k, v in (tags or {}).items()
            ]

            stack_exists = self._stack_exists(stack_name)

            if stack_exists:
                console.print(f"[yellow]Updating stack: {stack_name}[/yellow]")
                operation = 'update'
                self.cfn.update_stack(
                    StackName=stack_name,
                    TemplateBody=template_body,
                    Parameters=cfn_parameters,
                    Capabilities=capabilities or ['CAPABILITY_NAMED_IAM'],
                    Tags=cfn_tags
                )
            else:
                console.print(f"[green]Creating stack: {stack_name}[/green]")
                operation = 'create'
                self.cfn.create_stack(
                    StackName=stack_name,
                    TemplateBody=template_body,
                    Parameters=cfn_parameters,
                    Capabilities=capabilities or ['CAPABILITY_NAMED_IAM'],
                    Tags=cfn_tags
                )

            return self._wait_for_stack_completion(stack_name, operation)

        except ClientError as e:
            if 'No updates are to be performed' in str(e):
                console.print(f"[yellow]No changes detected for {stack_name}[/yellow]")
                return True
            console.print(f"[red]CloudFormation deployment failed: {e}[/red]")
            return False

    def get_stack_output(self, stack_name: str, output_key: str) -> Optional[str]:
        """Get specific output value from stack."""
        try:
            response = self.cfn.describe_stacks(StackName=stack_name)
            stack = response['Stacks'][0]

            for output in stack.get('Outputs', []):
                if output['OutputKey'] == output_key:
                    return output['OutputValue']

            return None
        except ClientError:
            return None

    def delete_stack(self, stack_name: str) -> bool:
        """Delete CloudFormation stack."""
        try:
            if not self._stack_exists(stack_name):
                console.print(f"[yellow]Stack {stack_name} does not exist[/yellow]")
                return True

            self.cfn.delete_stack(StackName=stack_name)

            waiter = self.cfn.get_waiter('stack_delete_complete')

            with Progress(
                SpinnerColumn(),
                TextColumn("[progress.description]{task.description}"),
                console=console,
            ) as progress:
                task = progress.add_task("Deleting stack...", total=None)

                try:
                    waiter.wait(
                        StackName=stack_name,
                        WaiterConfig={'Delay': 15, 'MaxAttempts': 120}
                    )
                    progress.update(task, description="Stack deletion completed")
                    return True
                except Exception as e:
                    console.print(f"[red]Stack deletion failed: {e}[/red]")
                    return False

        except ClientError as e:
            console.print(f"[red]Failed to delete stack: {e}[/red]")
            return False

    def _stack_exists(self, stack_name: str) -> bool:
        """Check if stack exists."""
        try:
            self.cfn.describe_stacks(StackName=stack_name)
            return True
        except ClientError as e:
            if 'does not exist' in str(e):
                return False
            raise

    def _wait_for_stack_completion(self, stack_name: str, operation: str) -> bool:
        """Wait for stack operation to complete."""
        if operation == 'create':
            waiter = self.cfn.get_waiter('stack_create_complete')
            success_status = 'CREATE_COMPLETE'
            failure_statuses = ['CREATE_FAILED', 'ROLLBACK_COMPLETE']
        else:
            waiter = self.cfn.get_waiter('stack_update_complete')
            success_status = 'UPDATE_COMPLETE'
            failure_statuses = ['UPDATE_FAILED', 'UPDATE_ROLLBACK_COMPLETE']

        with Progress(
            SpinnerColumn(),
            TextColumn("[progress.description]{task.description}"),
            console=console,
        ) as progress:
            task = progress.add_task(f"Waiting for stack {operation}...", total=None)

            try:
                waiter.wait(
                    StackName=stack_name,
                    WaiterConfig={'Delay': 15, 'MaxAttempts': 120}
                )
                progress.update(task, description=f"Stack {operation} completed")
                return True
            except Exception as e:
                try:
                    response = self.cfn.describe_stacks(StackName=stack_name)
                    status = response['Stacks'][0]['StackStatus']

                    if status in failure_statuses:
                        console.print(f"[red]Stack {operation} failed: {status}[/red]")
                        return False
                    elif status == success_status:
                        return True
                    else:
                        console.print(f"[yellow]Stack in unexpected status: {status}[/yellow]")
                        return False
                except Exception:
                    console.print(f"[red]Failed to check stack status: {e}[/red]")
                    return False
