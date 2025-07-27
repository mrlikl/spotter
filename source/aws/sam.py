"""SAM deployment utilities."""

import subprocess
from typing import Dict, Optional
from rich.console import Console
from rich.progress import Progress, SpinnerColumn, TextColumn

console = Console()


class SAMDeployer:
    """SAM deployment wrapper."""

    def _check_prerequisites(self) -> bool:
        """Check if SAM CLI is available."""
        try:
            subprocess.run(
                ["sam", "--version"],
                capture_output=True,
                text=True,
                check=True
            )
            return True
        except (subprocess.CalledProcessError, FileNotFoundError):
            console.print("[red]❌ SAM CLI not found[/red]")
            console.print("Install SAM CLI: https://docs.aws.amazon.com/serverless-application-model/latest/developerguide/install-sam-cli.html")
            return False

    def deploy(
        self,
        stack_name: str,
        region: str,
        template_path: str,
        parameters: Dict[str, str],
        capabilities: list,
        confirm_changeset: bool = True,
        tags: Optional[Dict[str, str]] = None
    ) -> bool:
        """Deploy CloudFormation stack using SAM."""

        if not self._check_prerequisites():
            return False

        param_overrides = []
        for key, value in parameters.items():
            param_overrides.extend(["--parameter-overrides", f"{key}={value}"])

        tag_overrides = []
        if tags:
            for key, value in tags.items():
                tag_overrides.extend(["--tags", f"{key}={value}"])

        deploy_cmd = [
            "sam", "deploy",
            "--template-file", template_path,
            "--stack-name", stack_name,
            "--region", region,
            "--capabilities", " ".join(capabilities),
            "--no-fail-on-empty-changeset",
            "--resolve-s3"
        ]

        if param_overrides:
            deploy_cmd.extend(param_overrides)

        if tag_overrides:
            deploy_cmd.extend(tag_overrides)

        if not confirm_changeset:
            deploy_cmd.append("--no-confirm-changeset")

        try:
            with Progress(
                SpinnerColumn(),
                TextColumn("[progress.description]{task.description}"),
                console=console,
            ) as progress:
                task = progress.add_task("Deploying CloudFormation stack...", total=None)

                result = subprocess.run(
                    deploy_cmd,
                    capture_output=True,
                    text=True,
                    check=True
                )

                progress.update(task, description="CloudFormation stack deployed")

            return True

        except subprocess.CalledProcessError as e:
            console.print(f"[red]CloudFormation deployment failed[/red]")
            if e.stderr:
                console.print(f"[red]{e.stderr}[/red]")
            return False

    def delete_stack(self, stack_name: str, region: str) -> bool:
        """Delete CloudFormation stack using SAM."""

        if not self._check_prerequisites():
            return False

        delete_cmd = [
            "sam", "delete",
            "--stack-name", stack_name,
            "--region", region,
            "--no-prompts"
        ]

        try:
            with Progress(
                SpinnerColumn(),
                TextColumn("[progress.description]{task.description}"),
                console=console,
            ) as progress:
                task = progress.add_task("Deleting CloudFormation stack...", total=None)

                subprocess.run(
                    delete_cmd,
                    capture_output=True,
                    text=True,
                    check=True
                )

                progress.update(task, description="CloudFormation stack deleted")

            return True

        except subprocess.CalledProcessError as e:
            console.print(f"[red]CloudFormation stack deletion failed[/red]")
            if e.stderr:
                console.print(f"[red]{e.stderr}[/red]")
            return False
