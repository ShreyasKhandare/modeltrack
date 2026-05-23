"""
Core pipeline DAG framework for ModelTrack.

Provides Task, Pipeline, DAGExecutor, and PipelineResult classes.
"""

import asyncio
import inspect
import time
from collections import defaultdict, deque
from datetime import datetime, timezone
from typing import Any, Callable, Dict, List, Optional

from modeltrack.shared.errors import PipelineError, TaskError
from modeltrack.shared.logger import get_logger
from modeltrack.shared.utils import generate_id, timestamp_now

logger = get_logger(__name__)


class Task:
    """
    Represents a single unit of work in a pipeline DAG.

    Tasks can be chained using the ``>>`` operator to express
    execution dependencies.
    """

    def __init__(
        self, name: str, func: Callable, inputs: Optional[Dict[str, Any]] = None
    ):
        self.name = name
        self.func = func
        self.inputs: Dict[str, Any] = inputs or {}
        self._next_tasks: List["Task"] = []
        self._prev_tasks: List["Task"] = []

    # ── chaining ────────────────────────────────────────────────────────────

    def __rshift__(self, other: "Task") -> "Task":
        """
        Chain this task to *other* using the ``>>`` operator.

        Returns *other* so chains can be written as ``a >> b >> c``.
        """
        if not isinstance(other, Task):
            raise TypeError(f"Cannot chain Task with {type(other)!r}")
        self._next_tasks.append(other)
        other._prev_tasks.append(self)
        return other

    # ── execution ───────────────────────────────────────────────────────────

    def run(self, **kwargs: Any) -> Any:
        """
        Execute the task function.

        Merges stored ``inputs`` with any caller-supplied *kwargs*.
        Supports both sync and async callables.
        """
        merged = {**self.inputs, **kwargs}
        try:
            if asyncio.iscoroutinefunction(self.func):
                loop = asyncio.get_event_loop()
                return loop.run_until_complete(self.func(**merged))
            return self.func(**merged)
        except Exception as exc:
            raise TaskError(
                message=str(exc),
                task_name=self.name,
            ) from exc

    def __repr__(self) -> str:  # pragma: no cover
        return f"<Task name={self.name!r}>"


# ─────────────────────────────────────────────────────────────────────────────


class Pipeline:
    """
    A named, directed-acyclic graph (DAG) of :class:`Task` objects.

    Normally created via the :func:`pipeline` decorator rather than
    instantiated directly.
    """

    def __init__(self, name: str, func: Callable):
        self.name = name
        self._factory = func
        # Build the task graph by calling the factory
        self.tasks: List[Task] = []
        self._build()

    # ── internals ───────────────────────────────────────────────────────────

    def _build(self) -> None:
        """Call the decorated function to populate ``self.tasks``."""
        result = self._factory()
        if result is None:
            return
        # The factory may return a single Task, a list of Tasks, or None
        if isinstance(result, Task):
            self.tasks = list(self._collect_all_tasks(result))
        elif isinstance(result, (list, tuple)):
            seen: set = set()
            all_tasks: List[Task] = []
            for item in result:
                if isinstance(item, Task):
                    for t in self._collect_all_tasks(item):
                        if t.name not in seen:
                            seen.add(t.name)
                            all_tasks.append(t)
            self.tasks = all_tasks
        else:
            self.tasks = []

    @staticmethod
    def _collect_all_tasks(root: Task) -> List[Task]:
        """BFS-collect all tasks reachable from *root* (including backward)."""
        # First, walk backward to find true roots
        visited: set = set()
        queue: deque = deque([root])
        while queue:
            t = queue.popleft()
            if id(t) in visited:
                continue
            visited.add(id(t))
            for prev in t._prev_tasks:
                queue.append(prev)

        # Now BFS forward from all roots (tasks with no predecessors)
        roots = [t for t in [root] + list(queue) if not t._prev_tasks]
        # Re-collect in a proper BFS from real roots
        visited2: set = set()
        result: List[Task] = []
        fwd_queue: deque = deque()
        for t in roots:
            fwd_queue.append(t)
        # Actually do a proper traversal to collect unique tasks
        all_seen: set = set()
        all_tasks: List[Task] = []
        # Use the visited set from backward walk to get all tasks
        # Re-walk all tasks in visited
        task_objs = list(visited)  # these are id()s, not tasks — need to track objects
        # Redo with object tracking
        obj_visited: Dict[int, Task] = {}
        q2: deque = deque([root])
        while q2:
            t = q2.popleft()
            if id(t) in obj_visited:
                continue
            obj_visited[id(t)] = t
            for prev in t._prev_tasks:
                q2.append(prev)
            for nxt in t._next_tasks:
                q2.append(nxt)
        return list(obj_visited.values())

    def get_execution_order(self) -> List[Task]:
        """
        Return tasks in topological (dependency) order using Kahn's algorithm.

        Raises :class:`PipelineError` if a cycle is detected.
        """
        if not self.tasks:
            return []

        # Build name→task index
        by_name: Dict[str, Task] = {t.name: t for t in self.tasks}

        # Build in-degree map and adjacency list (by name)
        in_degree: Dict[str, int] = defaultdict(int)
        adj: Dict[str, List[str]] = defaultdict(list)

        for task in self.tasks:
            if task.name not in in_degree:
                in_degree[task.name] = 0
            for nxt in task._next_tasks:
                adj[task.name].append(nxt.name)
                in_degree[nxt.name] += 1

        queue: deque = deque([name for name, deg in in_degree.items() if deg == 0])
        order: List[Task] = []

        while queue:
            name = queue.popleft()
            order.append(by_name[name])
            for neighbor in adj[name]:
                in_degree[neighbor] -= 1
                if in_degree[neighbor] == 0:
                    queue.append(neighbor)

        if len(order) != len(self.tasks):
            raise PipelineError(
                f"Cycle detected in pipeline '{self.name}'. "
                f"Processed {len(order)}/{len(self.tasks)} tasks."
            )

        return order

    def to_dict(self) -> dict:
        """Serialise the pipeline to a plain dictionary."""
        return {
            "name": self.name,
            "tasks": [
                {
                    "name": t.name,
                    "next_tasks": [n.name for n in t._next_tasks],
                    "prev_tasks": [p.name for p in t._prev_tasks],
                }
                for t in self.tasks
            ],
        }

    def __repr__(self) -> str:  # pragma: no cover
        return f"<Pipeline name={self.name!r} tasks={[t.name for t in self.tasks]!r}>"


# ─────────────────────────────────────────────────────────────────────────────


def pipeline(name: str):
    """
    Decorator that turns a function into a :class:`Pipeline`.

    Usage::

        @pipeline("my_pipeline")
        def my_pipeline():
            a = Task("load", load_data)
            b = Task("transform", transform_data)
            a >> b
            return a
    """

    def decorator(func: Callable) -> Pipeline:
        return Pipeline(name, func)

    return decorator


# ─────────────────────────────────────────────────────────────────────────────


class PipelineResult:
    """Captures the outcome of a single pipeline execution."""

    def __init__(
        self,
        pipeline_run_id: str,
        status: str,
        results: Dict[str, Any],
        errors: Dict[str, str],
        duration_seconds: float,
    ):
        self.pipeline_run_id = pipeline_run_id
        self.status = status
        self.results: Dict[str, Any] = results
        self.errors: Dict[str, str] = errors
        self.duration_seconds = duration_seconds

    def __repr__(self) -> str:  # pragma: no cover
        return (
            f"<PipelineResult run_id={self.pipeline_run_id!r} "
            f"status={self.status!r} "
            f"duration={self.duration_seconds:.2f}s>"
        )


# ─────────────────────────────────────────────────────────────────────────────


class DAGExecutor:
    """
    Executes a :class:`Pipeline` in topological order, recording results
    in the database when a session is available.
    """

    def __init__(self, db_session=None):
        self._session = db_session

    # ── public API ──────────────────────────────────────────────────────────

    async def run(
        self, p: Pipeline, context: Optional[Dict[str, Any]] = None
    ) -> PipelineResult:
        """
        Execute all tasks in *p* in dependency order.

        Each task receives the outputs of its predecessors merged with
        *context* as keyword arguments.
        """
        context = context or {}
        run_id = generate_id()
        start_time = time.monotonic()
        started_at = datetime.now(timezone.utc)

        results: Dict[str, Any] = {}
        errors: Dict[str, str] = {}
        overall_status = "success"

        # Persist pipeline run record
        self._create_pipeline_run(run_id, p.name, started_at)

        try:
            execution_order = p.get_execution_order()
        except PipelineError as exc:
            self._update_pipeline_run(run_id, "failed", str(exc))
            return PipelineResult(
                pipeline_run_id=run_id,
                status="failed",
                results={},
                errors={"__pipeline__": str(exc)},
                duration_seconds=time.monotonic() - start_time,
            )

        for task in execution_order:
            # Gather predecessor outputs
            pred_outputs: Dict[str, Any] = {}
            for pred in task._prev_tasks:
                pred_result = results.get(pred.name)
                if isinstance(pred_result, dict):
                    pred_outputs.update(pred_result)

            # Merge context and predecessor outputs with task inputs
            task_kwargs = {**context, **pred_outputs}

            task_run_id = generate_id()
            task_started_at = datetime.now(timezone.utc)
            self._create_task_run(task_run_id, run_id, task.name, task_started_at)

            logger.info(
                "Running task",
                extra={"task": task.name, "pipeline_run_id": run_id},
            )

            try:
                if asyncio.iscoroutinefunction(task.func):
                    result = await task.func(**{**task.inputs, **task_kwargs})
                else:
                    result = await asyncio.get_event_loop().run_in_executor(
                        None,
                        lambda t=task, kw=task_kwargs: t.func(**{**t.inputs, **kw}),
                    )
                results[task.name] = result
                self._update_task_run(task_run_id, "success")
                logger.info(
                    "Task succeeded",
                    extra={"task": task.name, "pipeline_run_id": run_id},
                )
            except Exception as exc:
                err_msg = str(exc)
                errors[task.name] = err_msg
                overall_status = "failed"
                self._update_task_run(task_run_id, "failed", error=err_msg)
                logger.error(
                    "Task failed",
                    extra={
                        "task": task.name,
                        "error": err_msg,
                        "pipeline_run_id": run_id,
                    },
                )
                # Stop on first failure
                break

        duration = time.monotonic() - start_time
        self._update_pipeline_run(run_id, overall_status)

        return PipelineResult(
            pipeline_run_id=run_id,
            status=overall_status,
            results=results,
            errors=errors,
            duration_seconds=duration,
        )

    def run_sync(
        self, p: Pipeline, context: Optional[Dict[str, Any]] = None
    ) -> PipelineResult:
        """Synchronous wrapper around :meth:`run`."""
        try:
            loop = asyncio.get_running_loop()
        except RuntimeError:
            loop = None

        if loop and loop.is_running():
            # We're inside an existing event loop (e.g., pytest-asyncio)
            import concurrent.futures

            with concurrent.futures.ThreadPoolExecutor(max_workers=1) as executor:
                future = executor.submit(lambda: asyncio.run(self.run(p, context)))
                return future.result()
        else:
            return asyncio.run(self.run(p, context))

    # ── DB helpers (no-op when session is None) ─────────────────────────────

    def _create_pipeline_run(
        self, run_id: str, name: str, started_at: datetime
    ) -> None:
        if self._session is None:
            return
        try:
            from modeltrack.shared.database import PipelineRun

            record = PipelineRun(
                id=run_id,
                pipeline_name=name,
                status="running",
                started_at=started_at,
            )
            self._session.add(record)
            self._session.commit()
        except Exception as exc:
            logger.warning(
                "DB write failed (pipeline run create)", extra={"error": str(exc)}
            )

    def _update_pipeline_run(
        self, run_id: str, status: str, error: Optional[str] = None
    ) -> None:
        if self._session is None:
            return
        try:
            from modeltrack.shared.database import PipelineRun

            record = self._session.get(PipelineRun, run_id)
            if record:
                record.status = status
                record.completed_at = datetime.now(timezone.utc)
                if error:
                    record.error = error
                self._session.commit()
        except Exception as exc:
            logger.warning(
                "DB write failed (pipeline run update)", extra={"error": str(exc)}
            )

    def _create_task_run(
        self,
        task_run_id: str,
        pipeline_run_id: str,
        task_name: str,
        started_at: datetime,
    ) -> None:
        if self._session is None:
            return
        try:
            from modeltrack.shared.database import TaskRun

            record = TaskRun(
                id=task_run_id,
                pipeline_run_id=pipeline_run_id,
                task_name=task_name,
                status="running",
                started_at=started_at,
            )
            self._session.add(record)
            self._session.commit()
        except Exception as exc:
            logger.warning(
                "DB write failed (task run create)", extra={"error": str(exc)}
            )

    def _update_task_run(
        self, task_run_id: str, status: str, error: Optional[str] = None
    ) -> None:
        if self._session is None:
            return
        try:
            from modeltrack.shared.database import TaskRun

            record = self._session.get(TaskRun, task_run_id)
            if record:
                record.status = status
                record.completed_at = datetime.now(timezone.utc)
                if error:
                    record.error = error
                self._session.commit()
        except Exception as exc:
            logger.warning(
                "DB write failed (task run update)", extra={"error": str(exc)}
            )
