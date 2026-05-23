"""
FastAPI routes for pipeline operations.
"""

import json
from datetime import datetime
from typing import Optional

from fastapi import APIRouter, HTTPException, Query
from modeltrack.pipelines.storage import PipelineStorage
from modeltrack.shared.database import (
    get_session,
    PipelineRun,
    LineageNode,
    LineageEdge,
)
from modeltrack.shared.errors import PipelineError, ModelTrackError
from modeltrack.shared.logger import get_logger
from modeltrack.shared.utils import generate_id, timestamp_now

from .schemas import (
    PipelineRunRequestSchema,
    PipelineRunResponseSchema,
    ValidationRequestSchema,
    ValidationResponseSchema,
)

logger = get_logger(__name__)

router = APIRouter(prefix="/pipelines", tags=["pipelines"])


@router.post("/{pipeline_name}/run", response_model=PipelineRunResponseSchema)
async def run_pipeline(pipeline_name: str, req: PipelineRunRequestSchema):
    """
    Run a pipeline by name.

    - **pipeline_name**: Name of the pipeline to run
    - **req.pipeline_name**: Should match the URL parameter
    - **req.context**: Optional execution context
    """
    try:
        # Load pipeline from storage
        storage = PipelineStorage()
        pipeline = storage.load(pipeline_name)

        if pipeline is None:
            raise HTTPException(
                status_code=404, detail=f"Pipeline not found: {pipeline_name}"
            )

        # Create a pipeline run record
        run_id = generate_id()
        started_at = timestamp_now()

        with get_session() as session:
            run_record = PipelineRun(
                id=run_id,
                pipeline_name=pipeline_name,
                status="running",
                started_at=datetime.fromisoformat(started_at.replace("Z", "+00:00")),
            )
            session.add(run_record)
            session.commit()

        try:
            # Execute pipeline (simplified for now)
            results = {}
            errors = {}

            completed_at = timestamp_now()
            duration = (
                datetime.fromisoformat(completed_at.replace("Z", "+00:00"))
                - datetime.fromisoformat(started_at.replace("Z", "+00:00"))
            ).total_seconds()

            with get_session() as session:
                run = session.query(PipelineRun).filter_by(id=run_id).first()
                if run:
                    run.status = "completed"
                    run.completed_at = datetime.fromisoformat(
                        completed_at.replace("Z", "+00:00")
                    )
                    session.commit()

            return PipelineRunResponseSchema(
                pipeline_run_id=run_id,
                status="completed",
                started_at=started_at,
                completed_at=completed_at,
                duration_seconds=duration,
                results=results,
                errors=errors,
            )

        except Exception as exc:
            logger.error(f"Pipeline execution failed: {exc}")
            with get_session() as session:
                run = session.query(PipelineRun).filter_by(id=run_id).first()
                if run:
                    run.status = "failed"
                    run.error = str(exc)
                    run.completed_at = datetime.now()
                    session.commit()

            raise HTTPException(
                status_code=500, detail=f"Pipeline execution failed: {exc}"
            )

    except HTTPException:
        raise
    except Exception as exc:
        logger.error(f"Error running pipeline: {exc}")
        raise HTTPException(status_code=500, detail=str(exc))


@router.get("/{pipeline_name}/status")
async def get_pipeline_status(pipeline_name: str, run_id: Optional[str] = Query(None)):
    """
    Get pipeline status.

    - **pipeline_name**: Name of the pipeline
    - **run_id**: Optional specific run ID; if not provided, returns latest run
    """
    try:
        with get_session() as session:
            if run_id:
                run = session.query(PipelineRun).filter_by(id=run_id).first()
            else:
                run = (
                    session.query(PipelineRun)
                    .filter_by(pipeline_name=pipeline_name)
                    .order_by(PipelineRun.started_at.desc())
                    .first()
                )

            if not run:
                raise HTTPException(status_code=404, detail="Pipeline run not found")

            return {
                "pipeline_run_id": run.id,
                "pipeline_name": run.pipeline_name,
                "status": run.status,
                "started_at": run.started_at.isoformat() + "Z",
                "completed_at": (
                    run.completed_at.isoformat() + "Z" if run.completed_at else None
                ),
                "error": run.error,
            }

    except HTTPException:
        raise
    except Exception as exc:
        logger.error(f"Error getting pipeline status: {exc}")
        raise HTTPException(status_code=500, detail=str(exc))


@router.get("/{pipeline_name}/runs")
async def list_pipeline_runs(pipeline_name: str, limit: int = Query(10, ge=1, le=100)):
    """
    List recent pipeline runs.

    - **pipeline_name**: Name of the pipeline
    - **limit**: Maximum number of runs to return (default 10, max 100)
    """
    try:
        with get_session() as session:
            runs = (
                session.query(PipelineRun)
                .filter_by(pipeline_name=pipeline_name)
                .order_by(PipelineRun.started_at.desc())
                .limit(limit)
                .all()
            )

            return {
                "pipeline_name": pipeline_name,
                "total": len(runs),
                "runs": [
                    {
                        "run_id": r.id,
                        "status": r.status,
                        "started_at": r.started_at.isoformat() + "Z",
                        "completed_at": (
                            r.completed_at.isoformat() + "Z" if r.completed_at else None
                        ),
                    }
                    for r in runs
                ],
            }

    except Exception as exc:
        logger.error(f"Error listing pipeline runs: {exc}")
        raise HTTPException(status_code=500, detail=str(exc))


@router.get("/{pipeline_name}/lineage")
async def get_lineage(pipeline_name: str, run_id: str):
    """
    Get data lineage graph for a pipeline run.

    Returns nodes (tasks and data artifacts) and edges (dependencies).
    """
    try:
        with get_session() as session:
            # Verify run exists
            run = session.query(PipelineRun).filter_by(id=run_id).first()
            if not run:
                raise HTTPException(status_code=404, detail="Pipeline run not found")

            # Get lineage nodes
            nodes = session.query(LineageNode).filter_by(pipeline_run_id=run_id).all()

            # Get lineage edges
            edges = session.query(LineageEdge).filter_by(pipeline_run_id=run_id).all()

            return {
                "pipeline_name": pipeline_name,
                "run_id": run_id,
                "nodes": [
                    {
                        "id": n.id,
                        "name": n.name,
                        "type": n.node_type,
                        "metadata": (
                            json.loads(n.metadata_json) if n.metadata_json else {}
                        ),
                    }
                    for n in nodes
                ],
                "edges": [
                    {"source_id": e.source_id, "target_id": e.target_id} for e in edges
                ],
            }

    except HTTPException:
        raise
    except Exception as exc:
        logger.error(f"Error getting lineage: {exc}")
        raise HTTPException(status_code=500, detail=str(exc))


@router.post("/{pipeline_name}/validate")
async def validate_data(pipeline_name: str, req: ValidationRequestSchema):
    """
    Validate data against pipeline validators.

    - **pipeline_name**: Name of the pipeline
    - **req.data**: List of dictionaries to validate
    """
    try:
        # Load pipeline from storage
        storage = PipelineStorage()
        pipeline = storage.load(pipeline_name)

        if pipeline is None:
            raise HTTPException(
                status_code=404, detail=f"Pipeline not found: {pipeline_name}"
            )

        # Validate data (simplified validation for now)
        total = len(req.data)
        valid_count = total  # Placeholder: real validation would check each record

        warnings = []
        errors = []

        if total == 0:
            warnings.append({"code": "empty_data", "message": "No data provided"})

        return ValidationResponseSchema(
            valid=len(errors) == 0,
            valid_pct=(valid_count / total * 100) if total > 0 else 0.0,
            total_records=total,
            valid_records=valid_count,
            warnings=warnings,
            errors=errors,
        )

    except HTTPException:
        raise
    except Exception as exc:
        logger.error(f"Error validating data: {exc}")
        raise HTTPException(status_code=500, detail=str(exc))
