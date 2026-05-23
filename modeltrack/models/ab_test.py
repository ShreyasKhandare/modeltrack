"""
A/B testing framework for comparing two model versions in production.
"""

import json
import math
from datetime import datetime, timezone
from typing import Dict, List, Optional, Tuple

from modeltrack.shared.errors import ABTestError
from modeltrack.shared.logger import get_logger
from modeltrack.shared.utils import generate_id, timestamp_now

logger = get_logger(__name__)


def _mean(values: List[float]) -> float:
    return sum(values) / len(values) if values else 0.0


def _std(values: List[float]) -> float:
    if len(values) < 2:
        return 0.0
    m = _mean(values)
    variance = sum((x - m) ** 2 for x in values) / (len(values) - 1)
    return math.sqrt(variance)


def _mae(predictions: List[float], actuals: List[float]) -> float:
    if not predictions:
        return 0.0
    return sum(abs(p - a) for p, a in zip(predictions, actuals)) / len(predictions)


def _rmse(predictions: List[float], actuals: List[float]) -> float:
    if not predictions:
        return 0.0
    return math.sqrt(
        sum((p - a) ** 2 for p, a in zip(predictions, actuals)) / len(predictions)
    )


def _welch_t_test(
    x1: List[float], x2: List[float]
) -> Tuple[float, float]:
    """
    Welch's two-sample t-test.

    Returns (t_statistic, p_value).
    Falls back to (0.0, 1.0) when inputs are degenerate.
    """
    n1, n2 = len(x1), len(x2)
    if n1 < 2 or n2 < 2:
        return 0.0, 1.0

    m1, m2 = _mean(x1), _mean(x2)
    s1, s2 = _std(x1), _std(x2)
    v1, v2 = (s1 ** 2) / n1, (s2 ** 2) / n2
    denom = math.sqrt(v1 + v2)
    if denom == 0:
        return 0.0, 1.0

    t_stat = (m1 - m2) / denom

    # Welch–Satterthwaite degrees of freedom
    df_num = (v1 + v2) ** 2
    df_den = (v1 ** 2) / (n1 - 1) + (v2 ** 2) / (n2 - 1)
    if df_den == 0:
        return t_stat, 1.0
    df = df_num / df_den

    # Approximate two-sided p-value via regularised incomplete beta
    p_value = _p_from_t(abs(t_stat), df)
    return t_stat, p_value


def _p_from_t(t: float, df: float) -> float:
    """
    Approximate two-sided p-value using the t-distribution CDF.

    Uses scipy when available; falls back to a simple approximation.
    """
    try:
        from scipy import stats as _stats

        return float(_stats.t.sf(t, df) * 2)
    except Exception:
        # Very rough approximation: use normal distribution
        z = t
        p = math.erfc(abs(z) / math.sqrt(2))
        return p


# ─────────────────────────── ABTest ──────────────────────────────────────────


class ABTest:
    """
    Manages an A/B experiment comparing two model variants.

    Parameters
    ----------
    name:
        Human-readable test name.
    model_a:
        Model A identifier string, e.g. ``"churn_model:1.0.0"``.
    model_b:
        Model B identifier string.
    traffic_split:
        Fraction of traffic routed to model B (0.0–1.0).
    db_session:
        Optional SQLAlchemy session for persistence.
    """

    def __init__(
        self,
        name: str,
        model_a: str,
        model_b: str,
        traffic_split: float = 0.1,
        db_session=None,
    ):
        self.name = name
        self.model_a = model_a
        self.model_b = model_b
        self.traffic_split = traffic_split
        self._session = db_session

        self.test_id: Optional[str] = None
        self.status: str = "created"
        self._winner: Optional[str] = None
        self.created_at: str = timestamp_now()
        self.completed_at: Optional[str] = None

        # In-memory observations
        self._obs: Dict[str, List[dict]] = {"model_a": [], "model_b": []}

    # ── lifecycle ─────────────────────────────────────────────────────────────

    def start(self) -> str:
        """Register the test and return its ID."""
        self.test_id = generate_id()
        self.status = "running"

        if self._session is not None:
            self._create_db_record()

        logger.info(
            "A/B test started",
            extra={
                "test_id": self.test_id,
                "test_name": self.name,
                "model_a": self.model_a,
                "model_b": self.model_b,
            },
        )
        return self.test_id

    def complete(self, winner: Optional[str] = None) -> None:
        """Mark the test as completed."""
        self._winner = winner or self.winner()
        self.status = "completed"
        self.completed_at = timestamp_now()

        if self._session is not None and self.test_id:
            self._update_db_record()

        logger.info(
            "A/B test completed",
            extra={"test_id": self.test_id, "winner": self._winner},
        )

    def stop(self) -> None:
        """Stop the test without declaring a winner."""
        self.status = "stopped"
        self.completed_at = timestamp_now()
        if self._session is not None and self.test_id:
            self._update_db_record()

    # ── observation recording ─────────────────────────────────────────────────

    def record(
        self,
        model_key: str,
        prediction: float,
        actual: float,
        latency_ms: Optional[float] = None,
    ) -> None:
        """
        Record a single prediction-vs-actual observation.

        Parameters
        ----------
        model_key:
            ``"model_a"`` or ``"model_b"``.
        prediction:
            The model's predicted value.
        actual:
            The ground-truth value.
        latency_ms:
            Optional inference latency in milliseconds.
        """
        if model_key not in ("model_a", "model_b"):
            raise ABTestError(
                f"model_key must be 'model_a' or 'model_b', got {model_key!r}",
                test_id=self.test_id or "",
            )

        obs = {
            "id": generate_id(),
            "model_key": model_key,
            "prediction": float(prediction),
            "actual": float(actual),
            "timestamp": timestamp_now(),
            "latency_ms": float(latency_ms) if latency_ms is not None else None,
        }
        self._obs[model_key].append(obs)

        if self._session is not None and self.test_id:
            self._persist_observation(obs)

    # ── analytics ────────────────────────────────────────────────────────────

    def get_metrics(self) -> dict:
        """
        Return per-model summary metrics.

        Includes ``count``, ``mae``, ``rmse``, ``avg_latency_ms``.
        """
        result: dict = {}
        for key in ("model_a", "model_b"):
            obs_list = self._obs[key]
            preds = [o["prediction"] for o in obs_list]
            actuals = [o["actual"] for o in obs_list]
            latencies = [o["latency_ms"] for o in obs_list if o["latency_ms"] is not None]

            result[key] = {
                "count": len(obs_list),
                "mae": round(_mae(preds, actuals), 6),
                "rmse": round(_rmse(preds, actuals), 6),
                "avg_latency_ms": round(_mean(latencies), 4) if latencies else None,
            }
        return result

    def is_significant(self, alpha: float = 0.05) -> bool:
        """
        Return True if the difference between models is statistically
        significant at level *alpha* (two-sided Welch's t-test on errors).
        """
        errors_a = [
            o["prediction"] - o["actual"] for o in self._obs["model_a"]
        ]
        errors_b = [
            o["prediction"] - o["actual"] for o in self._obs["model_b"]
        ]
        if len(errors_a) < 2 or len(errors_b) < 2:
            return False
        _, p_value = _welch_t_test(errors_a, errors_b)
        return p_value < alpha

    def winner(self) -> Optional[str]:
        """
        Return the winning model key based on lower RMSE.

        Returns ``None`` if observations are insufficient or the difference
        is not statistically significant.
        """
        if self._winner is not None:
            return self._winner

        metrics = self.get_metrics()
        a_count = metrics["model_a"]["count"]
        b_count = metrics["model_b"]["count"]
        if a_count == 0 or b_count == 0:
            return None

        if not self.is_significant():
            return None

        rmse_a = metrics["model_a"]["rmse"]
        rmse_b = metrics["model_b"]["rmse"]
        if rmse_a < rmse_b:
            return "model_a"
        elif rmse_b < rmse_a:
            return "model_b"
        return None  # exact tie

    # ── persistence ──────────────────────────────────────────────────────────

    @classmethod
    def load(cls, test_id: str, db_session=None) -> "ABTest":
        """
        Re-construct an :class:`ABTest` from its database record.

        Raises :class:`ABTestError` if *test_id* is not found.
        """
        if db_session is None:
            raise ABTestError(
                "Cannot load ABTest without a db_session",
                test_id=test_id,
            )

        from modeltrack.shared.database import ABTestObservation, ABTestRecord

        record = db_session.get(ABTestRecord, test_id)
        if record is None:
            raise ABTestError(
                f"ABTest not found: {test_id!r}",
                test_id=test_id,
            )

        obj = cls(
            name=record.test_name,
            model_a=record.model_a,
            model_b=record.model_b,
            traffic_split=record.traffic_split,
            db_session=db_session,
        )
        obj.test_id = record.id
        obj.status = record.status
        obj._winner = record.winner
        obj.created_at = record.created_at.isoformat()
        obj.completed_at = record.completed_at.isoformat() if record.completed_at else None

        # Reload observations
        obs_records = (
            db_session.query(ABTestObservation)
            .filter(ABTestObservation.test_id == test_id)
            .all()
        )
        for obs in obs_records:
            obj._obs[obs.model_key].append(
                {
                    "id": obs.id,
                    "model_key": obs.model_key,
                    "prediction": obs.prediction,
                    "actual": obs.actual,
                    "timestamp": obs.timestamp.isoformat(),
                    "latency_ms": obs.latency_ms,
                }
            )

        return obj

    # ── private DB helpers ────────────────────────────────────────────────────

    def _create_db_record(self) -> None:
        try:
            from modeltrack.shared.database import ABTestRecord

            record = ABTestRecord(
                id=self.test_id,
                test_name=self.name,
                model_a=self.model_a,
                model_b=self.model_b,
                traffic_split=self.traffic_split,
                status=self.status,
                created_at=datetime.now(timezone.utc),
                results_json="{}",
            )
            self._session.add(record)
            self._session.commit()
        except Exception as exc:
            logger.warning("DB write failed (ab test create)", extra={"error": str(exc)})

    def _update_db_record(self) -> None:
        try:
            from modeltrack.shared.database import ABTestRecord

            record = self._session.get(ABTestRecord, self.test_id)
            if record:
                record.status = self.status
                record.winner = self._winner
                if self.completed_at:
                    record.completed_at = datetime.fromisoformat(
                        self.completed_at.replace("Z", "+00:00")
                    )
                record.results_json = json.dumps(self.get_metrics())
                self._session.commit()
        except Exception as exc:
            logger.warning("DB write failed (ab test update)", extra={"error": str(exc)})

    def _persist_observation(self, obs: dict) -> None:
        try:
            from modeltrack.shared.database import ABTestObservation

            record = ABTestObservation(
                id=obs["id"],
                test_id=self.test_id,
                model_key=obs["model_key"],
                prediction=obs["prediction"],
                actual=obs["actual"],
                timestamp=datetime.fromisoformat(obs["timestamp"].replace("Z", "+00:00")),
                latency_ms=obs["latency_ms"],
            )
            self._session.add(record)
            self._session.commit()
        except Exception as exc:
            logger.warning(
                "DB write failed (ab test observation)", extra={"error": str(exc)}
            )
