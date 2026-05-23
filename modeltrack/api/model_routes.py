"""
FastAPI routes for model registry operations.
"""

import json
from datetime import datetime
from typing import Optional

from fastapi import APIRouter, HTTPException, Query
from modeltrack.models.registry import ModelRegistry, VALID_STAGES
from modeltrack.shared.database import get_session, ModelRecord
from modeltrack.shared.errors import (
    ModelNotFoundError,
    ModelAlreadyExistsError,
    PromotionError,
)
from modeltrack.shared.logger import get_logger
from modeltrack.shared.utils import generate_id, timestamp_now

from .schemas import (
    ModelSaveRequestSchema,
    ModelResponseSchema,
    ModelPromoteRequestSchema,
    ModelCompareResponseSchema,
)

logger = get_logger(__name__)

router = APIRouter(prefix="/models", tags=["models"])


@router.post("/{model_name}/register", response_model=ModelResponseSchema)
async def register_model(model_name: str, req: ModelSaveRequestSchema):
    """
    Register a new model version.

    - **model_name**: Name of the model
    - **req.version**: Version identifier
    - **req.metrics**: Performance metrics dictionary
    - **req.hyperparameters**: Optional hyperparameters
    - **req.description**: Optional description
    """
    try:
        registry = ModelRegistry()

        # Check if version already exists
        try:
            existing = registry.get(model_name, req.version)
            raise HTTPException(
                status_code=409,
                detail=f"Model version already exists: {model_name}:{req.version}",
            )
        except ModelNotFoundError:
            pass  # Expected: version doesn't exist yet

        # Register the model
        created_at = timestamp_now()
        model_id = generate_id("model_")

        with get_session() as session:
            record = ModelRecord(
                id=model_id,
                name=model_name,
                version=req.version,
                stage="dev",
                model_path="",  # Placeholder
                metrics_json=json.dumps(req.metrics),
                hyperparams_json=json.dumps(req.hyperparameters or {}),
                created_at=datetime.fromisoformat(created_at.replace("Z", "+00:00")),
                promoted_at=None,
                is_active=True,
            )
            session.add(record)
            session.commit()

        logger.info(
            f"Model registered: {model_name}:{req.version}",
            extra={"model_name": model_name, "version": req.version},
        )

        return ModelResponseSchema(
            name=model_name,
            version=req.version,
            stage="dev",
            metrics=req.metrics,
            hyperparameters=req.hyperparameters or {},
            created_at=created_at,
            promoted_at=None,
        )

    except HTTPException:
        raise
    except Exception as exc:
        logger.error(f"Error registering model: {exc}")
        raise HTTPException(status_code=500, detail=str(exc))


@router.get("/{model_name}/{version}", response_model=ModelResponseSchema)
async def get_model(model_name: str, version: str):
    """
    Get a specific model version.

    - **model_name**: Name of the model
    - **version**: Version identifier
    """
    try:
        with get_session() as session:
            record = (
                session.query(ModelRecord)
                .filter_by(name=model_name, version=version)
                .first()
            )

            if not record:
                raise HTTPException(
                    status_code=404,
                    detail=f"Model not found: {model_name}:{version}",
                )

            metrics = (
                json.loads(record.metrics_json) if record.metrics_json else {}
            )
            hyperparams = (
                json.loads(record.hyperparams_json)
                if record.hyperparams_json
                else {}
            )

            return ModelResponseSchema(
                name=record.name,
                version=record.version,
                stage=record.stage,
                metrics=metrics,
                hyperparameters=hyperparams,
                created_at=record.created_at.isoformat() + "Z",
                promoted_at=record.promoted_at.isoformat() + "Z" if record.promoted_at else None,
            )

    except HTTPException:
        raise
    except Exception as exc:
        logger.error(f"Error getting model: {exc}")
        raise HTTPException(status_code=500, detail=str(exc))


@router.get("/{model_name}/production", response_model=ModelResponseSchema)
async def get_production_model(model_name: str):
    """
    Get the current production stage model.

    - **model_name**: Name of the model
    """
    try:
        with get_session() as session:
            record = (
                session.query(ModelRecord)
                .filter_by(name=model_name, stage="production")
                .order_by(ModelRecord.promoted_at.desc())
                .first()
            )

            if not record:
                raise HTTPException(
                    status_code=404,
                    detail=f"No production model found for: {model_name}",
                )

            metrics = (
                json.loads(record.metrics_json) if record.metrics_json else {}
            )
            hyperparams = (
                json.loads(record.hyperparams_json)
                if record.hyperparams_json
                else {}
            )

            return ModelResponseSchema(
                name=record.name,
                version=record.version,
                stage=record.stage,
                metrics=metrics,
                hyperparameters=hyperparams,
                created_at=record.created_at.isoformat() + "Z",
                promoted_at=record.promoted_at.isoformat() + "Z" if record.promoted_at else None,
            )

    except HTTPException:
        raise
    except Exception as exc:
        logger.error(f"Error getting production model: {exc}")
        raise HTTPException(status_code=500, detail=str(exc))


@router.get("/{model_name}/versions")
async def list_versions(model_name: str, limit: int = Query(10, ge=1, le=100)):
    """
    List all versions of a model.

    - **model_name**: Name of the model
    - **limit**: Maximum number of versions to return
    """
    try:
        with get_session() as session:
            records = (
                session.query(ModelRecord)
                .filter_by(name=model_name)
                .order_by(ModelRecord.created_at.desc())
                .limit(limit)
                .all()
            )

            return {
                "model_name": model_name,
                "total": len(records),
                "versions": [
                    {
                        "version": r.version,
                        "stage": r.stage,
                        "created_at": r.created_at.isoformat() + "Z",
                        "promoted_at": r.promoted_at.isoformat() + "Z" if r.promoted_at else None,
                    }
                    for r in records
                ],
            }

    except Exception as exc:
        logger.error(f"Error listing model versions: {exc}")
        raise HTTPException(status_code=500, detail=str(exc))


@router.post("/{model_name}/promote", response_model=dict)
async def promote_model(model_name: str, req: ModelPromoteRequestSchema):
    """
    Promote a model to a new stage.

    - **model_name**: Name of the model
    - **req.version**: Version to promote
    - **req.target_stage**: Target stage (staging or production)
    - **req.gates**: Optional quality gates to check
    """
    try:
        if req.target_stage not in VALID_STAGES:
            raise HTTPException(
                status_code=400,
                detail=f"Invalid stage: {req.target_stage}. Valid: {VALID_STAGES}",
            )

        with get_session() as session:
            record = (
                session.query(ModelRecord)
                .filter_by(name=model_name, version=req.version)
                .first()
            )

            if not record:
                raise HTTPException(
                    status_code=404,
                    detail=f"Model version not found: {model_name}:{req.version}",
                )

            # Check quality gates
            gates_passed = []
            if req.gates:
                metrics = (
                    json.loads(record.metrics_json)
                    if record.metrics_json
                    else {}
                )
                for gate in req.gates:
                    metric = gate.get("metric")
                    threshold = gate.get("threshold")
                    operator = gate.get("operator", ">=")

                    if metric not in metrics:
                        raise HTTPException(
                            status_code=400,
                            detail=f"Metric not found: {metric}",
                        )

                    metric_value = metrics[metric]
                    passed = False

                    if operator == ">=":
                        passed = metric_value >= threshold
                    elif operator == "<=":
                        passed = metric_value <= threshold
                    elif operator == ">":
                        passed = metric_value > threshold
                    elif operator == "<":
                        passed = metric_value < threshold

                    gates_passed.append(
                        {
                            "metric": metric,
                            "threshold": threshold,
                            "value": metric_value,
                            "passed": passed,
                        }
                    )

                    if not passed:
                        raise HTTPException(
                            status_code=400,
                            detail=f"Gate check failed: {metric} {operator} {threshold}",
                        )

            # Promote the model
            old_stage = record.stage
            record.stage = req.target_stage
            record.promoted_at = datetime.now()
            session.commit()

            logger.info(
                f"Model promoted: {model_name}:{req.version} from {old_stage} to {req.target_stage}",
                extra={
                    "model_name": model_name,
                    "version": req.version,
                    "old_stage": old_stage,
                    "new_stage": req.target_stage,
                },
            )

            return {
                "success": True,
                "old_stage": old_stage,
                "new_stage": req.target_stage,
                "gates_passed": gates_passed,
            }

    except HTTPException:
        raise
    except Exception as exc:
        logger.error(f"Error promoting model: {exc}")
        raise HTTPException(status_code=500, detail=str(exc))


@router.post("/{model_name}/rollback", response_model=dict)
async def rollback_model(
    model_name: str, to_version: Optional[str] = Query(None)
):
    """
    Rollback production model to a previous version.

    - **model_name**: Name of the model
    - **to_version**: Optional specific version to rollback to;
      if not provided, rolls back to the previous production version
    """
    try:
        with get_session() as session:
            # Get current production model
            current = (
                session.query(ModelRecord)
                .filter_by(name=model_name, stage="production")
                .order_by(ModelRecord.promoted_at.desc())
                .first()
            )

            if not current:
                raise HTTPException(
                    status_code=404,
                    detail=f"No production model found for: {model_name}",
                )

            # Find previous production version
            if to_version:
                previous = (
                    session.query(ModelRecord)
                    .filter_by(name=model_name, version=to_version)
                    .first()
                )
            else:
                previous = (
                    session.query(ModelRecord)
                    .filter_by(name=model_name, stage="production")
                    .filter(ModelRecord.promoted_at < current.promoted_at)
                    .order_by(ModelRecord.promoted_at.desc())
                    .first()
                )

            if not previous:
                raise HTTPException(
                    status_code=404,
                    detail="No previous production version found",
                )

            # Perform rollback
            current.stage = "staging"
            previous.stage = "production"
            previous.promoted_at = datetime.now()
            session.commit()

            logger.info(
                f"Model rolled back: {model_name} from {current.version} to {previous.version}",
                extra={
                    "model_name": model_name,
                    "from_version": current.version,
                    "to_version": previous.version,
                },
            )

            return {
                "success": True,
                "from_version": current.version,
                "to_version": previous.version,
            }

    except HTTPException:
        raise
    except Exception as exc:
        logger.error(f"Error rolling back model: {exc}")
        raise HTTPException(status_code=500, detail=str(exc))


@router.get("/{model_name}/compare", response_model=ModelCompareResponseSchema)
async def compare_versions(
    model_name: str, version_a: str = Query(...), version_b: str = Query(...)
):
    """
    Compare metrics between two model versions.

    - **model_name**: Name of the model
    - **version_a**: First version to compare
    - **version_b**: Second version to compare
    """
    try:
        with get_session() as session:
            record_a = (
                session.query(ModelRecord)
                .filter_by(name=model_name, version=version_a)
                .first()
            )
            record_b = (
                session.query(ModelRecord)
                .filter_by(name=model_name, version=version_b)
                .first()
            )

            if not record_a or not record_b:
                raise HTTPException(
                    status_code=404, detail="One or both model versions not found"
                )

            metrics_a = (
                json.loads(record_a.metrics_json) if record_a.metrics_json else {}
            )
            metrics_b = (
                json.loads(record_b.metrics_json) if record_b.metrics_json else {}
            )

            # Calculate improvements
            improvements = {}
            for key in metrics_a.keys():
                if key in metrics_b:
                    improvements[key] = metrics_b[key] - metrics_a[key]

            return ModelCompareResponseSchema(
                version_a=version_a,
                version_b=version_b,
                metrics_a=metrics_a,
                metrics_b=metrics_b,
                improvements=improvements,
            )

    except HTTPException:
        raise
    except Exception as exc:
        logger.error(f"Error comparing models: {exc}")
        raise HTTPException(status_code=500, detail=str(exc))
