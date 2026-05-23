"""
File-system storage for pipeline definitions.
"""

import json
import os
from typing import TYPE_CHECKING, List

from modeltrack.shared.logger import get_logger
from modeltrack.shared.utils import timestamp_now

if TYPE_CHECKING:
    from modeltrack.pipelines.core import Pipeline

logger = get_logger(__name__)


class PipelineStorage:
    """
    Persists :class:`~modeltrack.pipelines.core.Pipeline` definitions as JSON
    files on the local file system.
    """

    def __init__(self, storage_dir: str):
        self.storage_dir = storage_dir
        os.makedirs(storage_dir, exist_ok=True)

    def save_pipeline(self, pipeline: "Pipeline") -> str:
        """
        Save *pipeline* as a JSON file.

        Returns the path to the saved file.
        """
        payload = pipeline.to_dict()
        payload["saved_at"] = timestamp_now()

        path = os.path.join(self.storage_dir, f"{pipeline.name}.json")
        with open(path, "w", encoding="utf-8") as fh:
            json.dump(payload, fh, indent=2)

        logger.info(
            "Pipeline saved", extra={"pipeline_name": pipeline.name, "path": path}
        )
        return path

    def load_pipeline(self, name: str) -> dict:
        """
        Load the pipeline definition for *name*.

        Returns a dictionary (the stored JSON).
        Raises :class:`FileNotFoundError` if not found.
        """
        path = os.path.join(self.storage_dir, f"{name}.json")
        if not os.path.exists(path):
            raise FileNotFoundError(
                f"Pipeline not found: '{name}' (expected at {path})"
            )

        with open(path, "r", encoding="utf-8") as fh:
            data = json.load(fh)

        logger.info("Pipeline loaded", extra={"pipeline_name": name})
        return data

    def list_pipelines(self) -> List[dict]:
        """
        Return a list of summary dicts for all stored pipelines.

        Each dict contains at least ``name``, ``saved_at``, and ``task_count``.
        """
        results: List[dict] = []
        for filename in sorted(os.listdir(self.storage_dir)):
            if not filename.endswith(".json"):
                continue
            path = os.path.join(self.storage_dir, filename)
            try:
                with open(path, "r", encoding="utf-8") as fh:
                    data = json.load(fh)
                results.append(
                    {
                        "name": data.get("name", filename[:-5]),
                        "saved_at": data.get("saved_at"),
                        "task_count": len(data.get("tasks", [])),
                        "path": path,
                    }
                )
            except (json.JSONDecodeError, OSError) as exc:
                logger.warning(
                    "Failed to read pipeline file",
                    extra={"file": filename, "error": str(exc)},
                )
        return results

    def delete_pipeline(self, name: str) -> bool:
        """Delete the stored definition for *name*. Returns True if deleted."""
        path = os.path.join(self.storage_dir, f"{name}.json")
        if os.path.exists(path):
            os.remove(path)
            logger.info("Pipeline deleted", extra={"pipeline_name": name})
            return True
        return False
