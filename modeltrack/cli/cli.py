"""
Click CLI tool for ModelTrack - Manage pipelines, models, and A/B tests.
"""

import json
import sys
from pathlib import Path
from typing import Optional

import click
import requests
from tabulate import tabulate

from modeltrack.config import get_settings
from modeltrack.models.registry import ModelRegistry
from modeltrack.shared.database import init_db
from modeltrack.shared.logger import get_logger

logger = get_logger(__name__)

# ─────────────────────────────────────────────────────────────────────────────
# API Base Configuration
# ─────────────────────────────────────────────────────────────────────────────

API_BASE_URL = "http://localhost:8000"


def get_api_url(endpoint: str) -> str:
    """Construct full API URL."""
    return f"{API_BASE_URL}{endpoint}"


def make_request(method: str, endpoint: str, **kwargs) -> dict:
    """Make HTTP request to API with error handling."""
    url = get_api_url(endpoint)
    try:
        response = requests.request(method, url, timeout=10, **kwargs)
        response.raise_for_status()
        return response.json() if response.text else {}
    except requests.exceptions.ConnectionError:
        click.echo(
            f"Error: Cannot connect to API at {API_BASE_URL}. Is the server running?",
            err=True,
        )
        sys.exit(1)
    except requests.exceptions.HTTPError as e:
        error_msg = str(e)
        try:
            data = e.response.json()
            error_msg = data.get("detail", data.get("error", str(e)))
        except Exception:
            pass
        click.echo(f"API Error: {error_msg}", err=True)
        sys.exit(1)
    except Exception as e:
        click.echo(f"Error: {str(e)}", err=True)
        sys.exit(1)


# ─────────────────────────────────────────────────────────────────────────────
# CLI Commands - Main Group
# ─────────────────────────────────────────────────────────────────────────────


@click.group()
@click.version_option(version="0.2.0")
def cli():
    """ModelTrack CLI - Unified pipeline and model management tool."""
    pass


# ─────────────────────────────────────────────────────────────────────────────
# Pipeline Commands
# ─────────────────────────────────────────────────────────────────────────────


@cli.group()
def pipeline():
    """Manage pipelines."""
    pass


@pipeline.command()
@click.argument("name")
@click.option(
    "--context",
    default="{}",
    help="JSON context dict to pass to pipeline",
    type=str,
)
def run(name: str, context: str):
    """Run a pipeline by name."""
    try:
        ctx = json.loads(context) if context != "{}" else {}
    except json.JSONDecodeError as e:
        click.echo(f"Error: Invalid JSON context: {e}", err=True)
        sys.exit(1)

    req = {
        "pipeline_name": name,
        "context": ctx,
    }

    result = make_request("POST", f"/pipelines/{name}/run", json=req)

    click.echo(f"✓ Pipeline started: {result.get('pipeline_run_id')}")
    click.echo(f"  Status: {result.get('status')}")
    click.echo(f"  Started: {result.get('started_at')}")


@pipeline.command()
@click.argument("name")
@click.option("--run-id", default=None, help="Specific run ID to check")
def status(name: str, run_id: Optional[str]):
    """Get pipeline status."""
    endpoint = f"/pipelines/{name}/status"
    params = {}
    if run_id:
        params["run_id"] = run_id

    result = make_request("GET", endpoint, params=params)

    click.echo(f"Pipeline: {result.get('pipeline_name')}")
    click.echo(f"Run ID: {result.get('pipeline_run_id')}")
    click.echo(f"Status: {result.get('status')}")
    click.echo(f"Started: {result.get('started_at')}")
    if result.get("completed_at"):
        click.echo(f"Completed: {result.get('completed_at')}")
    if result.get("error"):
        click.echo(f"Error: {result.get('error')}", err=True)


@pipeline.command()
@click.argument("name")
@click.option("--limit", default=10, type=int, help="Number of runs to show")
def history(name: str, limit: int):
    """View pipeline execution history."""
    result = make_request("GET", f"/pipelines/{name}/runs", params={"limit": limit})

    if not result.get("runs"):
        click.echo(f"No runs found for pipeline: {name}")
        return

    table_data = [
        [
            r["run_id"],
            r["status"],
            r["started_at"],
            r["completed_at"] or "N/A",
        ]
        for r in result["runs"]
    ]

    click.echo(tabulate(
        table_data,
        headers=["Run ID", "Status", "Started At", "Completed At"],
        tablefmt="simple",
    ))


@pipeline.command()
@click.argument("name")
@click.argument("run_id")
def lineage(name: str, run_id: str):
    """Show data lineage for a pipeline run."""
    result = make_request("GET", f"/pipelines/{name}/lineage", params={"run_id": run_id})

    nodes = result.get("nodes", [])
    edges = result.get("edges", [])

    click.echo(f"Pipeline: {result.get('pipeline_name')}")
    click.echo(f"Run ID: {result.get('run_id')}")
    click.echo()
    click.echo("Nodes:")
    if nodes:
        table_data = [[n["id"], n["name"], n["type"]] for n in nodes]
        click.echo(tabulate(table_data, headers=["ID", "Name", "Type"], tablefmt="simple"))
    else:
        click.echo("  None")

    click.echo()
    click.echo("Edges:")
    if edges:
        table_data = [[e["source_id"], "->", e["target_id"]] for e in edges]
        click.echo(tabulate(table_data, headers=["Source", "", "Target"], tablefmt="simple"))
    else:
        click.echo("  None")


# ─────────────────────────────────────────────────────────────────────────────
# Model Commands
# ─────────────────────────────────────────────────────────────────────────────


@cli.group()
def model():
    """Manage models."""
    pass


@model.command()
@click.argument("name")
@click.argument("version")
@click.option("--metrics", required=True, help="JSON metrics dict", type=str)
@click.option("--hyperparams", default="{}", help="JSON hyperparameters dict", type=str)
@click.option("--description", default="", help="Model description")
def save(name: str, version: str, metrics: str, hyperparams: str, description: str):
    """Register a new model version."""
    try:
        metrics_dict = json.loads(metrics)
        hyperparams_dict = json.loads(hyperparams)
    except json.JSONDecodeError as e:
        click.echo(f"Error: Invalid JSON input: {e}", err=True)
        sys.exit(1)

    req = {
        "name": name,
        "version": version,
        "metrics": metrics_dict,
        "hyperparameters": hyperparams_dict,
        "description": description,
    }

    result = make_request("POST", f"/models/{name}/register", json=req)

    click.echo(f"✓ Model registered: {result.get('name')}:{result.get('version')}")
    click.echo(f"  Stage: {result.get('stage')}")
    click.echo(f"  Created: {result.get('created_at')}")


@model.command()
@click.argument("name")
@click.option("--version", default=None, help="Specific version; if not provided shows all versions")
def get(name: str, version: Optional[str]):
    """Get model info."""
    if version:
        result = make_request("GET", f"/models/{name}/{version}")
        click.echo(f"Model: {result['name']}:{result['version']}")
        click.echo(f"Stage: {result['stage']}")
        click.echo(f"Created: {result['created_at']}")
        if result.get("promoted_at"):
            click.echo(f"Promoted: {result['promoted_at']}")
        click.echo(f"Metrics: {json.dumps(result['metrics'], indent=2)}")
        click.echo(f"Hyperparameters: {json.dumps(result['hyperparameters'], indent=2)}")
    else:
        result = make_request("GET", f"/models/{name}/versions")
        versions = result.get("versions", [])
        if not versions:
            click.echo(f"No versions found for model: {name}")
            return

        table_data = [
            [
                v["version"],
                v["stage"],
                v["created_at"],
                v["promoted_at"] or "N/A",
            ]
            for v in versions
        ]
        click.echo(tabulate(
            table_data,
            headers=["Version", "Stage", "Created At", "Promoted At"],
            tablefmt="simple",
        ))


@model.command()
@click.argument("name")
def versions(name: str):
    """List all versions of a model."""
    result = make_request("GET", f"/models/{name}/versions")

    versions = result.get("versions", [])
    if not versions:
        click.echo(f"No versions found for model: {name}")
        return

    table_data = [
        [
            v["version"],
            v["stage"],
            v["created_at"],
            v["promoted_at"] or "N/A",
        ]
        for v in versions
    ]

    click.echo(tabulate(
        table_data,
        headers=["Version", "Stage", "Created At", "Promoted At"],
        tablefmt="simple",
    ))


@model.command()
@click.argument("name")
@click.argument("version")
@click.argument("target_stage")
@click.option("--gates", default="[]", help="JSON quality gates", type=str)
def promote(name: str, version: str, target_stage: str, gates: str):
    """Promote model to a new stage."""
    try:
        gates_list = json.loads(gates)
    except json.JSONDecodeError as e:
        click.echo(f"Error: Invalid JSON gates: {e}", err=True)
        sys.exit(1)

    req = {
        "version": version,
        "target_stage": target_stage,
        "gates": gates_list,
    }

    result = make_request("POST", f"/models/{name}/promote", json=req)

    click.echo(f"✓ Model promoted: {name}:{version}")
    click.echo(f"  From: {result.get('old_stage')} → To: {result.get('new_stage')}")

    gates_passed = result.get("gates_passed", [])
    if gates_passed:
        click.echo("  Gates:")
        for gate in gates_passed:
            status = "PASS" if gate["passed"] else "FAIL"
            click.echo(
                f"    [{status}] {gate['metric']} {gate.get('threshold')} = {gate.get('value')}"
            )


@model.command()
@click.argument("name")
@click.option("--to-version", default=None, help="Specific version to rollback to")
def rollback(name: str, to_version: Optional[str]):
    """Rollback production model to a previous version."""
    params = {}
    if to_version:
        params["to_version"] = to_version

    result = make_request("POST", f"/models/{name}/rollback", params=params)

    click.echo(f"✓ Model rolled back: {name}")
    click.echo(f"  From: {result.get('from_version')}")
    click.echo(f"  To: {result.get('to_version')}")


# ─────────────────────────────────────────────────────────────────────────────
# A/B Test Commands
# ─────────────────────────────────────────────────────────────────────────────


@cli.group("test")
def test_group():
    """Manage A/B tests."""
    pass


@test_group.command()
@click.argument("name")
@click.argument("model_a")
@click.argument("model_b")
@click.option("--split", default=0.1, type=float, help="Traffic split for model B (0-1)")
def start(name: str, model_a: str, model_b: str, split: float):
    """Start an A/B test."""
    if not (0.0 <= split <= 1.0):
        click.echo("Error: Traffic split must be between 0 and 1", err=True)
        sys.exit(1)

    req = {
        "name": name,
        "model_a": model_a,
        "model_b": model_b,
        "traffic_split": split,
    }

    result = make_request("POST", "/ab-tests", json=req)

    click.echo(f"✓ A/B test started: {result.get('test_name')}")
    click.echo(f"  Test ID: {result.get('test_id')}")
    click.echo(f"  Model A: {model_a}")
    click.echo(f"  Model B: {model_b}")
    click.echo(f"  Traffic split: {split:.1%}")


@test_group.command()
@click.argument("test_id")
def results(test_id: str):
    """View A/B test results."""
    result = make_request("GET", f"/ab-tests/{test_id}/results")

    click.echo(f"Test: {result.get('test_name')}")
    click.echo(f"Status: {result.get('status')}")
    click.echo()
    click.echo("Model A Metrics:")
    click.echo(json.dumps(result.get("model_a_metrics", {}), indent=2))
    click.echo()
    click.echo("Model B Metrics:")
    click.echo(json.dumps(result.get("model_b_metrics", {}), indent=2))
    click.echo()
    if result.get("winner"):
        click.echo(f"Winner: {result.get('winner')}")
    click.echo(f"Significant: {result.get('significant')}")


# ─────────────────────────────────────────────────────────────────────────────
# Setup Commands
# ─────────────────────────────────────────────────────────────────────────────


@cli.command()
def init():
    """Initialize database and directories."""
    settings = get_settings()

    try:
        # Initialize database
        init_db()
        click.echo("✓ Database initialized")

        # Create model and pipeline directories
        Path(settings.MODELS_DIR).mkdir(parents=True, exist_ok=True)
        click.echo(f"✓ Created models directory: {settings.MODELS_DIR}")

        Path(settings.PIPELINES_DIR).mkdir(parents=True, exist_ok=True)
        click.echo(f"✓ Created pipelines directory: {settings.PIPELINES_DIR}")

        click.echo()
        click.echo("✓ ModelTrack initialized successfully!")

    except Exception as e:
        click.echo(f"Error: {str(e)}", err=True)
        sys.exit(1)


@cli.command()
def config():
    """Show current configuration."""
    settings = get_settings()

    config_data = {
        "API Host": settings.API_HOST,
        "API Port": settings.API_PORT,
        "Database URL": settings.DATABASE_URL,
        "Models Directory": settings.MODELS_DIR,
        "Pipelines Directory": settings.PIPELINES_DIR,
        "Log Level": settings.LOG_LEVEL,
    }

    for key, value in config_data.items():
        click.echo(f"{key}: {value}")


if __name__ == "__main__":
    cli()
