"""
Automated model retraining jobs for ModelTrack.
"""

from datetime import datetime, timezone
from typing import TYPE_CHECKING, Any, Callable, Dict, Optional

from modeltrack.shared.logger import get_logger
from modeltrack.shared.utils import generate_id, timestamp_now

if TYPE_CHECKING:
    from modeltrack.models.registry import ModelRegistry

logger = get_logger(__name__)

_SCHEDULE_SECONDS: Dict[str, int] = {
    "hourly": 3600,
    "daily": 86400,
    "weekly": 604800,
}


class RetrainingJob:
    """
    Encapsulates an automated retraining workflow.

    The caller provides a *train_func* that accepts optional *new_data* and
    returns a :class:`~modeltrack.models.registry.Model` instance.  When
    :meth:`trigger` is called the job will:

    1. Train a new model via *train_func*.
    2. Save it to the registry with an auto-incremented version.
    3. Compare its metrics against the current production model.
    4. Promote it if improvement exceeds *improvement_threshold*.

    Parameters
    ----------
    model_name:
        Logical name of the model family (e.g. ``"churn_predictor"``).
    train_func:
        Callable that trains a new model. Signature::

            def train_func(new_data=None) -> Model: ...

    schedule:
        Human-readable schedule string: ``"hourly"``, ``"daily"``,
        ``"weekly"``, or a cron expression (stored but not automatically
        executed — use an external scheduler).
    improvement_threshold:
        Minimum relative improvement in the primary metric (default 1 %).
    registry:
        :class:`~modeltrack.models.registry.ModelRegistry` instance.
    primary_metric:
        Name of the metric used to judge improvement (default ``"accuracy"``).
    higher_is_better:
        Whether a higher value of *primary_metric* is better (default True).
    """

    def __init__(
        self,
        model_name: str,
        train_func: Callable,
        schedule: str = "daily",
        improvement_threshold: float = 0.01,
        registry: Optional["ModelRegistry"] = None,
        primary_metric: str = "accuracy",
        higher_is_better: bool = True,
    ):
        self.model_name = model_name
        self.train_func = train_func
        self.schedule = schedule
        self.improvement_threshold = improvement_threshold
        self._registry = registry
        self.primary_metric = primary_metric
        self.higher_is_better = higher_is_better

        self.last_run_at: Optional[str] = None
        self.run_history: list = []

    # ── trigger ───────────────────────────────────────────────────────────────

    def trigger(self, new_data: Any = None) -> dict:
        """
        Run a training cycle.

        Returns
        -------
        dict
            Contains ``new_version``, ``metrics``, ``promoted``, and
            ``improvement`` keys.
        """
        run_id = generate_id()
        self.last_run_at = timestamp_now()
        logger.info(
            "Retraining job triggered",
            extra={"model_name": self.model_name, "run_id": run_id},
        )

        # ── 1. Train new model ──────────────────────────────────────────────
        try:
            new_model = self.train_func(new_data=new_data) if new_data is not None \
                else self.train_func()
        except TypeError:
            # Train func doesn't accept new_data
            new_model = self.train_func()

        # ── 2. Auto-increment version ───────────────────────────────────────
        if self._registry is not None:
            existing = self._registry.list_versions(self.model_name)
            new_model.name = self.model_name
            if existing:
                last_version = sorted(existing, key=lambda v: v["version"])[-1]["version"]
                new_model.version = self._bump_version(last_version)
            else:
                if not new_model.version:
                    new_model.version = "1.0.0"

            # ── 3. Save to registry ─────────────────────────────────────────
            try:
                self._registry.save(new_model)
            except Exception as exc:
                logger.error(
                    "Retraining: failed to save new model",
                    extra={"error": str(exc)},
                )
                raise

            # ── 4. Compare vs production ────────────────────────────────────
            promoted = False
            improvement: Optional[float] = None
            try:
                prod_model = self._registry.get_production(self.model_name)
                improved = self.evaluate_improvement(
                    prod_model.metrics, new_model.metrics
                )
                # Compute relative improvement
                old_val = prod_model.metrics.get(self.primary_metric, 0.0)
                new_val = new_model.metrics.get(self.primary_metric, 0.0)
                improvement = new_val - old_val

                if improved:
                    self._registry.promote(
                        self.model_name, new_model.version, "production"
                    )
                    promoted = True
                    logger.info(
                        "Retraining: new model promoted",
                        extra={
                            "version": new_model.version,
                            "improvement": improvement,
                        },
                    )
            except Exception as exc:
                # No production model yet — auto-promote
                logger.info(
                    "No production model found; auto-promoting new version",
                    extra={"version": new_model.version, "error": str(exc)},
                )
                self._registry.promote(self.model_name, new_model.version, "production")
                promoted = True

        else:
            promoted = False
            improvement = None

        result: dict = {
            "run_id": run_id,
            "new_version": new_model.version,
            "metrics": new_model.metrics,
            "promoted": promoted,
            "improvement": improvement,
            "triggered_at": self.last_run_at,
        }
        self.run_history.append(result)
        return result

    # ── evaluation ────────────────────────────────────────────────────────────

    def evaluate_improvement(
        self, old_metrics: dict, new_metrics: dict
    ) -> bool:
        """
        Return True if *new_metrics* improves over *old_metrics* by at least
        *improvement_threshold* on the primary metric.
        """
        old_val = old_metrics.get(self.primary_metric)
        new_val = new_metrics.get(self.primary_metric)

        if old_val is None or new_val is None:
            return False

        old_val = float(old_val)
        new_val = float(new_val)

        if self.higher_is_better:
            return new_val >= old_val + self.improvement_threshold
        else:
            return new_val <= old_val - self.improvement_threshold

    # ── private helpers ───────────────────────────────────────────────────────

    @staticmethod
    def _bump_version(version: str) -> str:
        """Increment the patch component of a semver string."""
        parts = version.lstrip("v").split(".")
        try:
            parts[-1] = str(int(parts[-1]) + 1)
        except (ValueError, IndexError):
            parts.append("1")
        return ".".join(parts)
