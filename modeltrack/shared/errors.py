"""
Custom exception hierarchy for ModelTrack.
"""


class ModelTrackError(Exception):
    """Base exception for all ModelTrack errors."""

    def __init__(self, message: str = "", details: dict = None):
        self.message = message
        self.details = details or {}
        super().__init__(message)

    def __repr__(self) -> str:
        return f"{self.__class__.__name__}(message={self.message!r}, details={self.details!r})"


# ──────────────────────────── Pipeline errors ────────────────────────────────


class PipelineError(ModelTrackError):
    """Raised when a pipeline-level error occurs (e.g., cycle detected)."""


class TaskError(ModelTrackError):
    """Raised when a task fails during execution."""

    def __init__(self, message: str = "", task_name: str = "", details: dict = None):
        self.task_name = task_name
        super().__init__(message, details)


class ValidationError(ModelTrackError):
    """Raised when data validation fails."""

    def __init__(
        self, message: str = "", validation_errors: list = None, details: dict = None
    ):
        self.validation_errors = validation_errors or []
        super().__init__(message, details)


# ──────────────────────────── Model / Registry errors ────────────────────────


class ModelNotFoundError(ModelTrackError):
    """Raised when a requested model does not exist in the registry."""

    def __init__(self, name: str, version: str = None, stage: str = None):
        self.model_name = name
        self.model_version = version
        self.model_stage = stage
        parts = [f"name={name!r}"]
        if version:
            parts.append(f"version={version!r}")
        if stage:
            parts.append(f"stage={stage!r}")
        message = f"Model not found: {', '.join(parts)}"
        super().__init__(message)


class ModelAlreadyExistsError(ModelTrackError):
    """Raised when trying to register a model that already exists."""

    def __init__(self, name: str, version: str):
        self.model_name = name
        self.model_version = version
        message = f"Model already exists: name={name!r}, version={version!r}"
        super().__init__(message)


# ──────────────────────────── A/B test errors ────────────────────────────────


class ABTestError(ModelTrackError):
    """Raised when an A/B test operation fails."""

    def __init__(self, message: str = "", test_id: str = "", details: dict = None):
        self.test_id = test_id
        super().__init__(message, details)


class PromotionError(ModelTrackError):
    """Raised when a model promotion fails gate checks or is otherwise invalid."""

    def __init__(
        self, message: str = "", gates_failed: list = None, details: dict = None
    ):
        self.gates_failed = gates_failed or []
        super().__init__(message, details)


# ──────────────────────────── Database errors ────────────────────────────────


class DatabaseError(ModelTrackError):
    """Raised when a database operation fails."""
