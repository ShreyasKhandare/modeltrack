"""
Shared utility helpers for ModelTrack.
"""

import hashlib
import json
import uuid
from datetime import datetime, timezone
from typing import Any


def generate_id() -> str:
    """Return a short, URL-safe unique identifier (first 8 hex chars of a UUID4)."""
    return uuid.uuid4().hex[:12]


def timestamp_now() -> str:
    """Return the current UTC time as an ISO-8601 string."""
    return datetime.now(tz=timezone.utc).isoformat()


class _NumpyEncoder(json.JSONEncoder):
    """JSON encoder that handles numpy scalar / array types."""

    def default(self, obj: Any) -> Any:
        # numpy is an optional heavy dependency; guard with try/except
        try:
            import numpy as np  # noqa: PLC0415

            if isinstance(obj, np.integer):
                return int(obj)
            if isinstance(obj, np.floating):
                return float(obj)
            if isinstance(obj, np.ndarray):
                return obj.tolist()
            if isinstance(obj, np.bool_):
                return bool(obj)
        except ImportError:
            pass

        # pandas Timestamp
        try:
            import pandas as pd  # noqa: PLC0415

            if isinstance(obj, pd.Timestamp):
                return obj.isoformat()
        except ImportError:
            pass

        # datetime / date
        if isinstance(obj, datetime):
            return obj.isoformat()

        return super().default(obj)


def safe_json_dumps(obj: Any, **kwargs) -> str:
    """
    Serialize *obj* to a JSON string, handling numpy types, datetime, etc.

    Parameters
    ----------
    obj:
        The object to serialize.
    **kwargs:
        Additional keyword arguments forwarded to :func:`json.dumps`.
    """
    return json.dumps(obj, cls=_NumpyEncoder, **kwargs)


def compute_hash(data: bytes) -> str:
    """Return the SHA-256 hex digest of *data*."""
    return hashlib.sha256(data).hexdigest()
