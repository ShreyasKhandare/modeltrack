"""
Binary model storage (joblib) for ModelTrack.
"""

import os
from typing import Any

import joblib

from modeltrack.shared.logger import get_logger

logger = get_logger(__name__)


class ModelStorage:
    """Persists and retrieves model binaries using :mod:`joblib`."""

    def __init__(self, storage_dir: str):
        self.storage_dir = storage_dir
        os.makedirs(storage_dir, exist_ok=True)

    def save_binary(self, model_obj: Any, name: str, version: str) -> str:
        """
        Serialise *model_obj* to disk and return the file path.

        The binary is saved as:
        ``<storage_dir>/<name>/<version>/model.joblib``
        """
        model_dir = os.path.join(self.storage_dir, name, version)
        os.makedirs(model_dir, exist_ok=True)
        path = os.path.join(model_dir, "model.joblib")
        joblib.dump(model_obj, path)
        logger.info(
            "Model binary saved",
            extra={"model_name": name, "version": version, "path": path},
        )
        return path

    def load_binary(self, model_path: str) -> Any:
        """
        Load and return the model binary at *model_path*.

        Raises :class:`FileNotFoundError` if the path does not exist.
        """
        if not os.path.exists(model_path):
            raise FileNotFoundError(f"Model binary not found at: {model_path}")
        model_obj = joblib.load(model_path)
        logger.info("Model binary loaded", extra={"path": model_path})
        return model_obj

    def delete_binary(self, model_path: str) -> None:
        """Remove the binary at *model_path* if it exists."""
        if os.path.exists(model_path):
            os.remove(model_path)
            logger.info("Model binary deleted", extra={"path": model_path})
        else:
            logger.warning(
                "delete_binary: path not found",
                extra={"path": model_path},
            )
