"""
Low-level async execution helpers: retry, timeout, and checkpointing.
"""

import asyncio
import json
import os
import pickle
from typing import Any, Callable, Optional, Tuple

from modeltrack.shared.logger import get_logger

logger = get_logger(__name__)


async def run_with_retry(
    func: Callable,
    args: Tuple = (),
    kwargs: Optional[dict] = None,
    max_retries: int = 3,
    backoff_factor: float = 2.0,
) -> Any:
    """
    Execute *func* with exponential-backoff retry on failure.

    Parameters
    ----------
    func:
        Sync or async callable to execute.
    args:
        Positional arguments for *func*.
    kwargs:
        Keyword arguments for *func*.
    max_retries:
        Maximum number of attempts (default 3).
    backoff_factor:
        Multiplier applied to the wait time between attempts (default 2.0).
        Wait times: 1s, 2s, 4s, …
    """
    kwargs = kwargs or {}
    last_exc: Optional[Exception] = None
    wait = 1.0

    for attempt in range(1, max_retries + 1):
        try:
            if asyncio.iscoroutinefunction(func):
                return await func(*args, **kwargs)
            return func(*args, **kwargs)
        except Exception as exc:
            last_exc = exc
            logger.warning(
                "run_with_retry: attempt failed",
                extra={
                    "attempt": attempt,
                    "max_retries": max_retries,
                    "error": str(exc),
                },
            )
            if attempt < max_retries:
                await asyncio.sleep(wait)
                wait *= backoff_factor

    raise RuntimeError(
        f"Function {getattr(func, '__name__', str(func))!r} failed after "
        f"{max_retries} attempt(s). Last error: {last_exc}"
    ) from last_exc


async def run_with_timeout(
    func: Callable, timeout: float, *args: Any, **kwargs: Any
) -> Any:
    """
    Execute *func* with a wall-clock *timeout* (seconds).

    Raises :class:`asyncio.TimeoutError` if *func* does not finish in time.
    """
    if asyncio.iscoroutinefunction(func):
        coro = func(*args, **kwargs)
    else:
        loop = asyncio.get_event_loop()
        coro = loop.run_in_executor(None, lambda: func(*args, **kwargs))

    return await asyncio.wait_for(coro, timeout=timeout)


# ─────────────────────────── CheckpointManager ───────────────────────────────


class CheckpointManager:
    """
    Simple file-system-based checkpoint store.

    Saves Python objects as pickle files under *checkpoint_dir*.
    Keys are sanitised to be safe filenames.
    """

    def __init__(self, checkpoint_dir: str):
        self.checkpoint_dir = checkpoint_dir
        os.makedirs(checkpoint_dir, exist_ok=True)

    # ── public API ───────────────────────────────────────────────────────────

    def save(self, key: str, data: Any) -> None:
        """Persist *data* under *key*."""
        path = self._path(key)
        with open(path, "wb") as fh:
            pickle.dump(data, fh, protocol=pickle.HIGHEST_PROTOCOL)
        logger.info("Checkpoint saved", extra={"key": key, "path": path})

    def load(self, key: str) -> Any:
        """
        Load and return the data stored under *key*.

        Raises :class:`KeyError` if the checkpoint does not exist.
        """
        path = self._path(key)
        if not os.path.exists(path):
            raise KeyError(f"Checkpoint not found: {key!r}")
        with open(path, "rb") as fh:
            data = pickle.load(fh)
        logger.info("Checkpoint loaded", extra={"key": key, "path": path})
        return data

    def exists(self, key: str) -> bool:
        """Return True if a checkpoint for *key* exists on disk."""
        return os.path.exists(self._path(key))

    def delete(self, key: str) -> None:
        """Remove the checkpoint for *key* if it exists."""
        path = self._path(key)
        if os.path.exists(path):
            os.remove(path)

    # ── private helpers ──────────────────────────────────────────────────────

    def _path(self, key: str) -> str:
        safe_key = key.replace("/", "_").replace("\\", "_").replace(":", "_")
        return os.path.join(self.checkpoint_dir, f"{safe_key}.pkl")
