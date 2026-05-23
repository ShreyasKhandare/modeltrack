"""
FastAPI routes for A/B test operations.
"""

import json
from datetime import datetime
from typing import Optional

from fastapi import APIRouter, HTTPException, Query
from modeltrack.shared.database import (
    get_session,
    ABTestRecord,
    ABTestObservation,
)
from modeltrack.shared.logger import get_logger
from modeltrack.shared.utils import generate_id, timestamp_now

from .schemas import (
    ABTestStartSchema,
    ABTestRecordSchema,
    ABTestResultsSchema,
)

logger = get_logger(__name__)

router = APIRouter(prefix="/ab-tests", tags=["ab-tests"])


@router.post("/", response_model=dict)
async def start_ab_test(req: ABTestStartSchema):
    """
    Start a new A/B test.

    - **req.name**: Test name
    - **req.model_a**: Model A identifier
    - **req.model_b**: Model B identifier
    - **req.traffic_split**: Traffic allocation for model B (0-1)
    """
    try:
        test_id = generate_id()
        created_at = timestamp_now()

        with get_session() as session:
            record = ABTestRecord(
                id=test_id,
                test_name=req.name,
                model_a=req.model_a,
                model_b=req.model_b,
                traffic_split=req.traffic_split,
                status="running",
                winner=None,
                created_at=datetime.fromisoformat(created_at.replace("Z", "+00:00")),
                completed_at=None,
                results_json=None,
            )
            session.add(record)
            session.commit()

        logger.info(
            f"A/B test started: {req.name}",
            extra={"test_id": test_id, "test_name": req.name},
        )

        return {
            "test_id": test_id,
            "test_name": req.name,
            "status": "running",
            "created_at": created_at,
        }

    except Exception as exc:
        logger.error(f"Error starting A/B test: {exc}")
        raise HTTPException(status_code=500, detail=str(exc))


@router.post("/{test_id}/record")
async def record_observation(test_id: str, req: ABTestRecordSchema):
    """
    Record an observation (prediction + actual) for an A/B test.

    - **test_id**: Test ID
    - **req.model_key**: Which model (model_a or model_b)
    - **req.prediction**: Predicted value
    - **req.actual**: Actual outcome
    - **req.latency_ms**: Optional latency in milliseconds
    """
    try:
        timestamp = timestamp_now()

        with get_session() as session:
            # Verify test exists
            test = session.query(ABTestRecord).filter_by(id=test_id).first()
            if not test:
                raise HTTPException(status_code=404, detail=f"Test not found: {test_id}")

            if test.status != "running":
                raise HTTPException(
                    status_code=400,
                    detail=f"Test is not running: {test.status}",
                )

            observation_id = generate_id()
            obs = ABTestObservation(
                id=observation_id,
                test_id=test_id,
                model_key=req.model_key,
                prediction=req.prediction,
                actual=req.actual,
                timestamp=datetime.fromisoformat(timestamp.replace("Z", "+00:00")),
                latency_ms=req.latency_ms,
            )
            session.add(obs)
            session.commit()

        logger.info(
            f"A/B test observation recorded: {test_id}",
            extra={"test_id": test_id, "model_key": req.model_key},
        )

        return {
            "observation_id": observation_id,
            "test_id": test_id,
            "model_key": req.model_key,
            "recorded_at": timestamp,
        }

    except HTTPException:
        raise
    except Exception as exc:
        logger.error(f"Error recording observation: {exc}")
        raise HTTPException(status_code=500, detail=str(exc))


@router.get("/{test_id}/results", response_model=ABTestResultsSchema)
async def get_results(test_id: str):
    """
    Get current results of an A/B test.

    - **test_id**: Test ID
    """
    try:
        with get_session() as session:
            test = session.query(ABTestRecord).filter_by(id=test_id).first()
            if not test:
                raise HTTPException(status_code=404, detail=f"Test not found: {test_id}")

            # Get observations for both models
            obs_a = (
                session.query(ABTestObservation)
                .filter_by(test_id=test_id, model_key="model_a")
                .all()
            )
            obs_b = (
                session.query(ABTestObservation)
                .filter_by(test_id=test_id, model_key="model_b")
                .all()
            )

            # Calculate metrics
            def calc_metrics(observations):
                if not observations:
                    return {}

                predictions = [o.prediction for o in observations]
                actuals = [o.actual for o in observations]

                # Simple accuracy-like metric (count of close predictions)
                close = sum(
                    1 for p, a in zip(predictions, actuals) if abs(p - a) < 0.5
                )
                accuracy = close / len(predictions)

                # Mean absolute error
                mae = sum(abs(p - a) for p, a in zip(predictions, actuals)) / len(
                    predictions
                )

                # Average latency
                latencies = [o.latency_ms for o in observations if o.latency_ms]
                avg_latency = (
                    sum(latencies) / len(latencies) if latencies else None
                )

                return {
                    "accuracy": round(accuracy, 4),
                    "mae": round(mae, 4),
                    "n_observations": len(observations),
                    "avg_latency_ms": round(avg_latency, 2) if avg_latency else None,
                }

            metrics_a = calc_metrics(obs_a)
            metrics_b = calc_metrics(obs_b)

            # Determine winner
            winner = None
            if metrics_a and metrics_b:
                if metrics_a.get("accuracy", 0) > metrics_b.get("accuracy", 0):
                    winner = "model_a"
                elif metrics_b.get("accuracy", 0) > metrics_a.get("accuracy", 0):
                    winner = "model_b"

            return ABTestResultsSchema(
                test_name=test.test_name,
                status=test.status,
                model_a_metrics=metrics_a,
                model_b_metrics=metrics_b,
                winner=winner,
                significant=abs(
                    metrics_a.get("accuracy", 0) - metrics_b.get("accuracy", 0)
                )
                > 0.05,
            )

    except HTTPException:
        raise
    except Exception as exc:
        logger.error(f"Error getting A/B test results: {exc}")
        raise HTTPException(status_code=500, detail=str(exc))


@router.post("/{test_id}/complete", response_model=dict)
async def complete_test(test_id: str, winner: Optional[str] = Query(None)):
    """
    Mark an A/B test as complete.

    - **test_id**: Test ID
    - **winner**: Optional winner (model_a or model_b);
      if not specified, winner is auto-determined from results
    """
    try:
        with get_session() as session:
            test = session.query(ABTestRecord).filter_by(id=test_id).first()
            if not test:
                raise HTTPException(status_code=404, detail=f"Test not found: {test_id}")

            if test.status != "running":
                raise HTTPException(
                    status_code=400,
                    detail=f"Test is not running: {test.status}",
                )

            # If winner not specified, determine from results
            if not winner:
                obs_a = (
                    session.query(ABTestObservation)
                    .filter_by(test_id=test_id, model_key="model_a")
                    .all()
                )
                obs_b = (
                    session.query(ABTestObservation)
                    .filter_by(test_id=test_id, model_key="model_b")
                    .all()
                )

                if obs_a and obs_b:
                    acc_a = sum(
                        1
                        for o in obs_a
                        if abs(o.prediction - o.actual) < 0.5
                    ) / len(obs_a)
                    acc_b = sum(
                        1
                        for o in obs_b
                        if abs(o.prediction - o.actual) < 0.5
                    ) / len(obs_b)

                    winner = "model_a" if acc_a > acc_b else "model_b"

            test.status = "completed"
            test.winner = winner
            test.completed_at = datetime.now()
            session.commit()

            logger.info(
                f"A/B test completed: {test.test_name}",
                extra={"test_id": test_id, "winner": winner},
            )

            return {
                "success": True,
                "test_id": test_id,
                "test_name": test.test_name,
                "status": "completed",
                "winner": winner,
            }

    except HTTPException:
        raise
    except Exception as exc:
        logger.error(f"Error completing A/B test: {exc}")
        raise HTTPException(status_code=500, detail=str(exc))


@router.get("/")
async def list_tests(limit: int = Query(10, ge=1, le=100)):
    """
    List active and recent A/B tests.

    - **limit**: Maximum number of tests to return (default 10, max 100)
    """
    try:
        with get_session() as session:
            tests = (
                session.query(ABTestRecord)
                .order_by(ABTestRecord.created_at.desc())
                .limit(limit)
                .all()
            )

            return {
                "total": len(tests),
                "tests": [
                    {
                        "test_id": t.id,
                        "test_name": t.test_name,
                        "status": t.status,
                        "model_a": t.model_a,
                        "model_b": t.model_b,
                        "winner": t.winner,
                        "created_at": t.created_at.isoformat() + "Z",
                        "completed_at": t.completed_at.isoformat() + "Z" if t.completed_at else None,
                    }
                    for t in tests
                ],
            }

    except Exception as exc:
        logger.error(f"Error listing A/B tests: {exc}")
        raise HTTPException(status_code=500, detail=str(exc))
