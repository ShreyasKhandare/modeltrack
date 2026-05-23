"""
Model registry: save, retrieve, version, and promote ML models.
"""

import json
import os
import re
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from modeltrack.models.storage import ModelStorage
from modeltrack.shared.errors import ModelAlreadyExistsError, ModelNotFoundError
from modeltrack.shared.logger import get_logger
from modeltrack.shared.utils import generate_id, safe_json_dumps, timestamp_now

logger = get_logger(__name__)

VALID_STAGES = {"dev", "staging", "production"}


# ─────────────────────────── Model dataclass ─────────────────────────────────


class Model:
    """
    Represents a trained ML model with metadata.

    Attributes
    ----------
    name:
        Logical model name (e.g. ``"churn_predictor"``).
    version:
        Semantic version string (e.g. ``"1.0.0"``).
    model_binary:
        The raw trained model object (sklearn estimator, etc.).
    metrics:
        Evaluation metrics (e.g. ``{"accuracy": 0.92}``).
    hyperparameters:
        Hyperparameter dict (e.g. ``{"n_estimators": 100}``).
    stage:
        Lifecycle stage: ``"dev"``, ``"staging"``, or ``"production"``.
    created_at:
        ISO-8601 string of creation time.
    description:
        Free-text description of the model.
    """

    def __init__(
        self,
        name: str,
        version: str,
        model_binary: Any = None,
        metrics: Optional[Dict[str, float]] = None,
        hyperparameters: Optional[Dict[str, Any]] = None,
        stage: str = "dev",
        created_at: Optional[str] = None,
        description: str = "",
        model_id: Optional[str] = None,
        model_path: Optional[str] = None,
    ):
        self.name = name
        self.version = version
        self.model_binary = model_binary
        self.metrics: Dict[str, float] = metrics or {}
        self.hyperparameters: Dict[str, Any] = hyperparameters or {}
        self.stage = stage
        self.created_at = created_at or timestamp_now()
        self.description = description
        self.model_id = model_id or generate_id()
        self.model_path = model_path

    def __repr__(self) -> str:  # pragma: no cover
        return (
            f"<Model name={self.name!r} version={self.version!r} stage={self.stage!r}>"
        )


# ─────────────────────────── Version comparison ───────────────────────────────


def _parse_version(v: str):
    """
    Parse a version string into a comparable tuple.

    Handles semver (``1.2.3``), simple numbers (``2``), and date-like
    strings (``20240101``).  Falls back to the raw string on failure.
    """
    cleaned = v.lstrip("v").strip()
    parts = re.split(r"[.\-_]", cleaned)
    result = []
    for p in parts:
        try:
            result.append(int(p))
        except ValueError:
            result.append(p)
    return tuple(result) if result else (v,)


def _version_lt(a: str, b: str) -> bool:
    """Return True if version *a* < version *b*."""
    try:
        return _parse_version(a) < _parse_version(b)
    except TypeError:
        return str(a) < str(b)


# ─────────────────────────── ModelRegistry ───────────────────────────────────


class ModelRegistry:
    """
    Central registry for managing ML model lifecycle.

    Supports saving, loading, promoting, and deleting models across
    dev / staging / production stages.
    """

    def __init__(
        self,
        backend: str = "sqlite",
        models_dir: str = "./models_store",
        db_session=None,
    ):
        self.backend = backend
        self.models_dir = models_dir
        self._session = db_session
        self._storage = ModelStorage(models_dir)

    # ── save ─────────────────────────────────────────────────────────────────

    def save(self, model: Model) -> str:
        """
        Persist *model* to disk and register it in the database.

        Returns the model's unique ID.
        Raises :class:`ModelAlreadyExistsError` if a model with the same
        name + version already exists.
        """
        if self._record_exists(model.name, model.version):
            raise ModelAlreadyExistsError(model.name, model.version)

        # Save binary
        model_path = self._storage.save_binary(
            model.model_binary, model.name, model.version
        )
        model.model_path = model_path

        # Save metadata in DB
        if self._session is not None:
            self._insert_record(model)

        logger.info(
            "Model saved",
            extra={
                "model_name": model.name,
                "version": model.version,
                "id": model.model_id,
            },
        )
        return model.model_id

    # ── get ──────────────────────────────────────────────────────────────────

    def get(
        self,
        name: str,
        version: Optional[str] = None,
        stage: Optional[str] = None,
    ) -> Model:
        """
        Retrieve a model by name + version or by name + stage.

        If neither *version* nor *stage* is given, returns the latest version.
        Raises :class:`ModelNotFoundError` if no match is found.
        """
        if self._session is None:
            raise ModelNotFoundError(name, version, stage)

        from modeltrack.shared.database import ModelRecord

        q = self._session.query(ModelRecord).filter(
            ModelRecord.name == name,
            ModelRecord.is_active == True,  # noqa: E712
        )

        if version is not None:
            q = q.filter(ModelRecord.version == version)
        if stage is not None:
            q = q.filter(ModelRecord.stage == stage)

        records = q.all()
        if not records:
            raise ModelNotFoundError(name, version, stage)

        # Pick latest by version
        record = sorted(records, key=lambda r: _parse_version(r.version))[-1]
        return self._record_to_model(record, load_binary=True)

    def get_production(self, name: str) -> Model:
        """Return the production model for *name*."""
        return self.get(name, stage="production")

    # ── list ─────────────────────────────────────────────────────────────────

    def list_versions(self, name: str) -> List[dict]:
        """Return metadata dicts for all versions of *name*."""
        if self._session is None:
            return []
        from modeltrack.shared.database import ModelRecord

        records = (
            self._session.query(ModelRecord)
            .filter(
                ModelRecord.name == name, ModelRecord.is_active == True  # noqa: E712
            )
            .all()
        )
        return [self._record_to_dict(r) for r in records]

    def list_all(self) -> List[dict]:
        """Return metadata dicts for every registered model."""
        if self._session is None:
            return []
        from modeltrack.shared.database import ModelRecord

        records = (
            self._session.query(ModelRecord)
            .filter(ModelRecord.is_active == True)  # noqa: E712
            .all()
        )
        return [self._record_to_dict(r) for r in records]

    # ── promote ───────────────────────────────────────────────────────────────

    def promote(self, name: str, version: str, target_stage: str) -> bool:
        """
        Move *name:version* to *target_stage*.

        Returns True on success.
        Raises :class:`ModelNotFoundError` / :class:`ValueError` on failure.
        """
        if target_stage not in VALID_STAGES:
            raise ValueError(
                f"Invalid stage {target_stage!r}. Must be one of {sorted(VALID_STAGES)}."
            )

        if self._session is None:
            raise ModelNotFoundError(name, version)

        from modeltrack.shared.database import ModelRecord

        record = (
            self._session.query(ModelRecord)
            .filter(
                ModelRecord.name == name,
                ModelRecord.version == version,
                ModelRecord.is_active == True,  # noqa: E712
            )
            .first()
        )
        if record is None:
            raise ModelNotFoundError(name, version)

        record.stage = target_stage
        record.promoted_at = datetime.now(timezone.utc)
        self._session.commit()

        logger.info(
            "Model promoted",
            extra={"model_name": name, "version": version, "stage": target_stage},
        )
        return True

    # ── delete ────────────────────────────────────────────────────────────────

    def delete(self, name: str, version: str) -> bool:
        """
        Soft-delete the model record (sets ``is_active = False``).

        Returns True if the record was found and deactivated.
        """
        if self._session is None:
            return False

        from modeltrack.shared.database import ModelRecord

        record = (
            self._session.query(ModelRecord)
            .filter(
                ModelRecord.name == name,
                ModelRecord.version == version,
                ModelRecord.is_active == True,  # noqa: E712
            )
            .first()
        )
        if record is None:
            return False

        record.is_active = False
        self._session.commit()

        logger.info(
            "Model soft-deleted", extra={"model_name": name, "version": version}
        )
        return True

    # ── compare ───────────────────────────────────────────────────────────────

    def compare_versions(self, name: str, version_a: str, version_b: str) -> dict:
        """
        Compare metrics between two versions of *name*.

        Returns a dict with ``model_a``, ``model_b``, and ``diff`` sections.
        """
        if self._session is None:
            raise ModelNotFoundError(name, version_a)

        from modeltrack.shared.database import ModelRecord

        def _get_record(v: str) -> ModelRecord:
            r = (
                self._session.query(ModelRecord)
                .filter(
                    ModelRecord.name == name,
                    ModelRecord.version == v,
                    ModelRecord.is_active == True,  # noqa: E712
                )
                .first()
            )
            if r is None:
                raise ModelNotFoundError(name, v)
            return r

        rec_a = _get_record(version_a)
        rec_b = _get_record(version_b)

        metrics_a = json.loads(rec_a.metrics_json or "{}")
        metrics_b = json.loads(rec_b.metrics_json or "{}")

        diff: Dict[str, Any] = {}
        all_keys = set(metrics_a) | set(metrics_b)
        for key in all_keys:
            va = metrics_a.get(key)
            vb = metrics_b.get(key)
            if isinstance(va, (int, float)) and isinstance(vb, (int, float)):
                diff[key] = {
                    "version_a": va,
                    "version_b": vb,
                    "delta": round(vb - va, 6),
                    "pct_change": (
                        round((vb - va) / abs(va) * 100, 2) if va != 0 else None
                    ),
                }
            else:
                diff[key] = {"version_a": va, "version_b": vb}

        return {
            "name": name,
            "model_a": {
                "version": version_a,
                "stage": rec_a.stage,
                "metrics": metrics_a,
            },
            "model_b": {
                "version": version_b,
                "stage": rec_b.stage,
                "metrics": metrics_b,
            },
            "diff": diff,
        }

    # ── private helpers ───────────────────────────────────────────────────────

    def _record_exists(self, name: str, version: str) -> bool:
        if self._session is None:
            return False
        from modeltrack.shared.database import ModelRecord

        return (
            self._session.query(ModelRecord)
            .filter(
                ModelRecord.name == name,
                ModelRecord.version == version,
                ModelRecord.is_active == True,  # noqa: E712
            )
            .count()
        ) > 0

    def _insert_record(self, model: Model) -> None:
        from modeltrack.shared.database import ModelRecord

        record = ModelRecord(
            id=model.model_id,
            name=model.name,
            version=model.version,
            stage=model.stage,
            model_path=model.model_path or "",
            metrics_json=safe_json_dumps(model.metrics),
            hyperparams_json=safe_json_dumps(model.hyperparameters),
            created_at=(
                datetime.fromisoformat(model.created_at.replace("Z", "+00:00"))
                if isinstance(model.created_at, str)
                else datetime.now(timezone.utc)
            ),
            is_active=True,
        )
        self._session.add(record)
        self._session.commit()

    def _record_to_model(self, record, load_binary: bool = False) -> Model:
        binary = None
        if load_binary and record.model_path and os.path.exists(record.model_path):
            try:
                binary = self._storage.load_binary(record.model_path)
            except Exception as exc:
                logger.warning(
                    "Could not load model binary",
                    extra={"model_path": record.model_path, "error": str(exc)},
                )

        return Model(
            name=record.name,
            version=record.version,
            model_binary=binary,
            metrics=json.loads(record.metrics_json or "{}"),
            hyperparameters=json.loads(record.hyperparams_json or "{}"),
            stage=record.stage,
            created_at=record.created_at.isoformat() if record.created_at else None,
            model_id=record.id,
            model_path=record.model_path,
        )

    @staticmethod
    def _record_to_dict(record) -> dict:
        return {
            "id": record.id,
            "name": record.name,
            "version": record.version,
            "stage": record.stage,
            "model_path": record.model_path,
            "metrics": json.loads(record.metrics_json or "{}"),
            "hyperparameters": json.loads(record.hyperparams_json or "{}"),
            "created_at": record.created_at.isoformat() if record.created_at else None,
            "promoted_at": (
                record.promoted_at.isoformat() if record.promoted_at else None
            ),
            "is_active": record.is_active,
        }
