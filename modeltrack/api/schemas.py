"""
Pydantic schemas for API requests and responses.
"""

from typing import Optional
from pydantic import BaseModel, Field


# ─────────────────────────── Pipeline Schemas ───────────────────────────────


class TaskSchema(BaseModel):
    """Schema for a pipeline task."""

    name: str = Field(..., description="Task name")
    inputs: dict = Field(default_factory=dict, description="Task inputs")
    outputs: list[str] = Field(default_factory=list, description="Output keys")

    class Config:
        json_schema_extra = {
            "example": {
                "name": "preprocess",
                "inputs": {"data_path": "/path/to/data.csv"},
                "outputs": ["processed_data"],
            }
        }


class PipelineRunRequestSchema(BaseModel):
    """Request to run a pipeline."""

    pipeline_name: str = Field(..., description="Name of the pipeline to run")
    context: dict = Field(default_factory=dict, description="Execution context")

    class Config:
        json_schema_extra = {
            "example": {
                "pipeline_name": "training_pipeline",
                "context": {"model_name": "churn_predictor"},
            }
        }


class PipelineRunResponseSchema(BaseModel):
    """Response from a pipeline run."""

    pipeline_run_id: str = Field(..., description="Unique run ID")
    status: str = Field(..., description="Run status (pending, running, completed, failed)")
    started_at: str = Field(..., description="ISO-8601 start time")
    completed_at: Optional[str] = Field(None, description="ISO-8601 completion time")
    duration_seconds: Optional[float] = Field(None, description="Execution duration")
    results: dict = Field(default_factory=dict, description="Execution results")
    errors: dict = Field(default_factory=dict, description="Errors if any")

    class Config:
        json_schema_extra = {
            "example": {
                "pipeline_run_id": "run_abc123",
                "status": "completed",
                "started_at": "2024-01-01T12:00:00Z",
                "completed_at": "2024-01-01T12:05:00Z",
                "duration_seconds": 300.0,
                "results": {"model_accuracy": 0.95},
                "errors": {},
            }
        }


class ValidationRequestSchema(BaseModel):
    """Request to validate data."""

    data: list[dict] = Field(..., description="Data records to validate")

    class Config:
        json_schema_extra = {
            "example": {
                "data": [
                    {"feature1": 1.0, "feature2": 2.0},
                    {"feature1": 3.0, "feature2": 4.0},
                ]
            }
        }


class ValidationResponseSchema(BaseModel):
    """Response from data validation."""

    valid: bool = Field(..., description="Overall validity")
    valid_pct: float = Field(..., description="Percentage of valid records")
    total_records: int = Field(..., description="Total records validated")
    valid_records: int = Field(..., description="Number of valid records")
    warnings: list[dict] = Field(default_factory=list, description="Validation warnings")
    errors: list[dict] = Field(default_factory=list, description="Validation errors")

    class Config:
        json_schema_extra = {
            "example": {
                "valid": True,
                "valid_pct": 100.0,
                "total_records": 100,
                "valid_records": 100,
                "warnings": [],
                "errors": [],
            }
        }


# ─────────────────────────── Model Schemas ──────────────────────────────────


class ModelSaveRequestSchema(BaseModel):
    """Request to register a model."""

    name: str = Field(..., description="Model name")
    version: str = Field(..., description="Model version")
    metrics: dict = Field(..., description="Model metrics")
    hyperparameters: dict = Field(default_factory=dict, description="Hyperparameters")
    description: str = Field(default="", description="Model description")

    class Config:
        json_schema_extra = {
            "example": {
                "name": "churn_predictor",
                "version": "1.0.0",
                "metrics": {"accuracy": 0.95, "auc": 0.92},
                "hyperparameters": {"n_estimators": 100, "max_depth": 10},
                "description": "Initial churn prediction model",
            }
        }


class ModelResponseSchema(BaseModel):
    """Response containing model information."""

    name: str = Field(..., description="Model name")
    version: str = Field(..., description="Model version")
    stage: str = Field(..., description="Model stage (dev, staging, production)")
    metrics: dict = Field(..., description="Model metrics")
    hyperparameters: dict = Field(..., description="Hyperparameters")
    created_at: str = Field(..., description="ISO-8601 creation time")
    promoted_at: Optional[str] = Field(None, description="ISO-8601 promotion time")

    class Config:
        json_schema_extra = {
            "example": {
                "name": "churn_predictor",
                "version": "1.0.0",
                "stage": "dev",
                "metrics": {"accuracy": 0.95, "auc": 0.92},
                "hyperparameters": {"n_estimators": 100},
                "created_at": "2024-01-01T12:00:00Z",
                "promoted_at": None,
            }
        }


class ModelPromoteRequestSchema(BaseModel):
    """Request to promote a model."""

    version: str = Field(..., description="Model version to promote")
    target_stage: str = Field(..., description="Target stage (staging or production)")
    gates: list[dict] = Field(
        default_factory=list,
        description="Quality gates {metric, threshold, operator}",
    )

    class Config:
        json_schema_extra = {
            "example": {
                "version": "1.0.0",
                "target_stage": "production",
                "gates": [
                    {"metric": "accuracy", "threshold": 0.90, "operator": ">="}
                ],
            }
        }


class ModelCompareResponseSchema(BaseModel):
    """Response from model comparison."""

    version_a: str = Field(..., description="First version")
    version_b: str = Field(..., description="Second version")
    metrics_a: dict = Field(..., description="Metrics for version A")
    metrics_b: dict = Field(..., description="Metrics for version B")
    improvements: dict = Field(..., description="Improvements in version B")


# ─────────────────────────── A/B Test Schemas ───────────────────────────────


class ABTestStartSchema(BaseModel):
    """Request to start an A/B test."""

    name: str = Field(..., description="Test name")
    model_a: str = Field(..., description="Model A identifier")
    model_b: str = Field(..., description="Model B identifier")
    traffic_split: float = Field(
        default=0.1, ge=0.0, le=1.0, description="Traffic split for B (0-1)"
    )

    class Config:
        json_schema_extra = {
            "example": {
                "name": "churn_test_v1",
                "model_a": "churn_predictor:1.0.0",
                "model_b": "churn_predictor:1.1.0",
                "traffic_split": 0.1,
            }
        }


class ABTestRecordSchema(BaseModel):
    """Request to record an A/B test observation."""

    model_key: str = Field(
        ..., description="Which model (model_a or model_b)", pattern="^(model_a|model_b)$"
    )
    prediction: float = Field(..., description="Model prediction")
    actual: float = Field(..., description="Actual outcome")
    latency_ms: Optional[float] = Field(None, description="Model latency in ms")

    class Config:
        json_schema_extra = {
            "example": {
                "model_key": "model_a",
                "prediction": 0.75,
                "actual": 1.0,
                "latency_ms": 45.2,
            }
        }


class ABTestResultsSchema(BaseModel):
    """Response with A/B test results."""

    test_name: str = Field(..., description="Test name")
    status: str = Field(..., description="Test status (running, completed)")
    model_a_metrics: dict = Field(..., description="Model A performance metrics")
    model_b_metrics: dict = Field(..., description="Model B performance metrics")
    winner: Optional[str] = Field(None, description="Winning model (model_a or model_b)")
    significant: bool = Field(..., description="Whether difference is statistically significant")

    class Config:
        json_schema_extra = {
            "example": {
                "test_name": "churn_test_v1",
                "status": "completed",
                "model_a_metrics": {"accuracy": 0.92, "auc": 0.88},
                "model_b_metrics": {"accuracy": 0.94, "auc": 0.91},
                "winner": "model_b",
                "significant": True,
            }
        }
