"""
Model promotion management with gate-based approval and rollback.
"""

import json
import operator as op
from datetime import datetime, timezone
from typing import TYPE_CHECKING, Any, Dict, List, Optional

from modeltrack.shared.errors import ModelNotFoundError, PromotionError
from modeltrack.shared.logger import get_logger
from modeltrack.shared.utils import generate_id, timestamp_now

if TYPE_CHECKING:
    from modeltrack.models.registry import ModelRegistry

logger = get_logger(__name__)

_OPERATORS = {
    ">=": op.ge,
    ">": op.gt,
    "<=": op.le,
    "<": op.lt,
    "==": op.eq,
    "!=": op.ne,
}


# ─────────────────────────── PromotionGate ───────────────────────────────────


class PromotionGate:
    """
    A single numeric gate that a model must pass before promotion.

    Example::

        gate = PromotionGate("accuracy", 0.90, ">=")
        gate.check({"accuracy": 0.92})  # True
    """

    def __init__(self, metric: str, threshold: float, operator: str = ">="):
        if operator not in _OPERATORS:
            raise ValueError(
                f"Unknown operator {operator!r}. "
                f"Valid operators: {sorted(_OPERATORS)}"
            )
        self.metric = metric
        self.threshold = threshold
        self.operator = operator
        self._op_func = _OPERATORS[operator]

    def check(self, metrics: dict) -> bool:
        """
        Return True if *metrics* satisfies this gate.

        Returns False (without raising) when the metric is missing.
        """
        value = metrics.get(self.metric)
        if value is None:
            return False
        try:
            return bool(self._op_func(float(value), float(self.threshold)))
        except (TypeError, ValueError):
            return False

    def to_dict(self) -> dict:
        return {
            "metric": self.metric,
            "operator": self.operator,
            "threshold": self.threshold,
        }

    def __repr__(self) -> str:  # pragma: no cover
        return (
            f"<PromotionGate {self.metric} {self.operator} {self.threshold}>"
        )


# ─────────────────────────── PromotionManager ────────────────────────────────


class PromotionManager:
    """
    Orchestrates model promotion with gate checks and audit trails.

    The audit trail is kept in-memory (list of dicts) and optionally
    persisted to the database.
    """

    STAGES: List[str] = ["dev", "staging", "production"]

    def __init__(self, registry: "ModelRegistry", db_session=None):
        self._registry = registry
        self._session = db_session
        self._audit_trail: Dict[str, List[dict]] = {}  # name -> list of events

    # ── promote ──────────────────────────────────────────────────────────────

    def promote(
        self,
        name: str,
        version: str,
        target_stage: str,
        gates: Optional[List[PromotionGate]] = None,
        approver: str = "system",
    ) -> dict:
        """
        Promote *name:version* to *target_stage* after checking *gates*.

        Parameters
        ----------
        name:
            Model name.
        version:
            Version to promote.
        target_stage:
            Destination stage (``"dev"``, ``"staging"``, or ``"production"``).
        gates:
            Optional list of metric gates that must pass.
        approver:
            Who/what initiated this promotion.

        Returns
        -------
        dict
            Contains ``success``, ``stage``, ``gates_passed``, and
            ``gates_failed`` keys.
        """
        if target_stage not in self.STAGES:
            raise ValueError(
                f"Invalid target_stage {target_stage!r}. "
                f"Must be one of {self.STAGES}."
            )

        # Fetch model metrics for gate evaluation
        model_metrics: dict = {}
        try:
            model = self._registry.get(name, version=version)
            model_metrics = model.metrics
        except ModelNotFoundError:
            raise

        # Evaluate gates
        gates_passed: List[dict] = []
        gates_failed: List[dict] = []
        for gate in (gates or []):
            passed = gate.check(model_metrics)
            gate_dict = gate.to_dict()
            gate_dict["value"] = model_metrics.get(gate.metric)
            gate_dict["passed"] = passed
            if passed:
                gates_passed.append(gate_dict)
            else:
                gates_failed.append(gate_dict)

        success = len(gates_failed) == 0

        event: dict = {
            "event_id": generate_id(),
            "name": name,
            "version": version,
            "target_stage": target_stage,
            "approver": approver,
            "timestamp": timestamp_now(),
            "gates_passed": gates_passed,
            "gates_failed": gates_failed,
            "success": success,
        }

        if success:
            self._registry.promote(name, version, target_stage)
            logger.info(
                "Promotion succeeded",
                extra={"model_name": name, "version": version, "stage": target_stage},
            )
        else:
            logger.warning(
                "Promotion blocked by gates",
                extra={
                    "model_name": name,
                    "version": version,
                    "stage": target_stage,
                    "failed_gates": gates_failed,
                },
            )
            raise PromotionError(
                message=(
                    f"Promotion of {name}:{version} to {target_stage!r} failed "
                    f"gate checks: {[g['metric'] for g in gates_failed]}"
                ),
                gates_failed=gates_failed,
            )

        # Record audit
        self._audit_trail.setdefault(name, []).append(event)

        return {
            "success": success,
            "stage": target_stage,
            "gates_passed": gates_passed,
            "gates_failed": gates_failed,
        }

    # ── rollback ──────────────────────────────────────────────────────────────

    def rollback(self, name: str, to_version: Optional[str] = None) -> dict:
        """
        Roll back the production model for *name* to *to_version*
        (or the previous production version if *to_version* is omitted).

        Returns a summary dict.
        """
        versions = self._registry.list_versions(name)
        if not versions:
            raise ModelNotFoundError(name)

        if to_version is None:
            # Find the last production version from audit trail
            trail = self._audit_trail.get(name, [])
            prod_events = [
                e for e in trail
                if e.get("target_stage") == "production" and e.get("success")
            ]
            if len(prod_events) < 2:
                # Fall back to second-latest version
                prod_versions = [v for v in versions if v["stage"] != "dev"]
                if len(prod_versions) < 1:
                    raise PromotionError(
                        f"No previous production version found for {name!r}"
                    )
                to_version = prod_versions[-1]["version"]
            else:
                to_version = prod_events[-2]["version"]

        # Promote to_version back to production
        result = self.promote(
            name=name,
            version=to_version,
            target_stage="production",
            gates=None,
            approver="rollback",
        )
        result["rolled_back_to"] = to_version
        return result

    # ── audit trail ───────────────────────────────────────────────────────────

    def get_audit_trail(self, name: str) -> List[dict]:
        """Return the promotion history for *name*."""
        return list(self._audit_trail.get(name, []))
