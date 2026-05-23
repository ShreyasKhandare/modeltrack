"""
Tests for modeltrack.pipelines.core — Task, Pipeline, DAGExecutor, PipelineResult.
"""

import asyncio
import pytest

from modeltrack.pipelines.core import (
    DAGExecutor,
    Pipeline,
    PipelineResult,
    Task,
    pipeline,
)
from modeltrack.shared.errors import PipelineError, TaskError


# ─────────────────────────── Helper functions ─────────────────────────────────


def add_one(x: int = 0) -> int:
    return x + 1


def double(x: int = 0) -> int:
    return x * 2


def failing_func(**kwargs):
    raise ValueError("deliberate failure")


def return_dict(**kwargs) -> dict:
    return {"result": 42, "extra": "data"}


async def async_add(x: int = 0) -> int:
    await asyncio.sleep(0)
    return x + 10


# ─────────────────────────── Task tests ──────────────────────────────────────


class TestTask:
    def test_task_creation(self):
        t = Task("my_task", add_one)
        assert t.name == "my_task"
        assert t.func is add_one
        assert t.inputs == {}
        assert t._next_tasks == []
        assert t._prev_tasks == []

    def test_task_creation_with_inputs(self):
        t = Task("my_task", add_one, inputs={"x": 5})
        assert t.inputs == {"x": 5}

    def test_task_run_basic(self):
        t = Task("add", add_one, inputs={"x": 3})
        result = t.run()
        assert result == 4

    def test_task_run_with_kwargs_override(self):
        t = Task("add", add_one, inputs={"x": 1})
        result = t.run(x=10)
        assert result == 11

    def test_task_rshift_returns_other(self):
        a = Task("a", add_one)
        b = Task("b", double)
        returned = a >> b
        assert returned is b

    def test_task_rshift_sets_next(self):
        a = Task("a", add_one)
        b = Task("b", double)
        a >> b
        assert b in a._next_tasks

    def test_task_rshift_sets_prev(self):
        a = Task("a", add_one)
        b = Task("b", double)
        a >> b
        assert a in b._prev_tasks

    def test_task_chain_three(self):
        a = Task("a", add_one)
        b = Task("b", double)
        c = Task("c", add_one)
        a >> b >> c
        assert b in a._next_tasks
        assert c in b._next_tasks
        assert a in b._prev_tasks
        assert b in c._prev_tasks

    def test_task_rshift_type_error(self):
        t = Task("t", add_one)
        with pytest.raises(TypeError):
            t >> "not_a_task"

    def test_task_run_raises_task_error(self):
        t = Task("fail", failing_func)
        with pytest.raises(TaskError) as exc_info:
            t.run()
        assert exc_info.value.task_name == "fail"

    def test_async_task_run(self):
        t = Task("async_add", async_add, inputs={"x": 5})
        result = t.run()
        assert result == 15


# ─────────────────────────── Pipeline tests ──────────────────────────────────


class TestPipeline:
    def test_pipeline_decorator_creates_pipeline(self):
        @pipeline("test_pipeline")
        def my_pipeline():
            return Task("only", add_one)

        assert isinstance(my_pipeline, Pipeline)
        assert my_pipeline.name == "test_pipeline"

    def test_pipeline_has_tasks(self):
        @pipeline("p")
        def p():
            a = Task("a", add_one)
            b = Task("b", double)
            a >> b
            return a

        assert len(p.tasks) == 2

    def test_pipeline_to_dict(self):
        @pipeline("p_dict")
        def p():
            a = Task("a", add_one)
            b = Task("b", double)
            a >> b
            return a

        d = p.to_dict()
        assert d["name"] == "p_dict"
        assert len(d["tasks"]) == 2

    def test_get_execution_order_single_task(self):
        @pipeline("single")
        def p():
            return Task("only", add_one)

        order = p.get_execution_order()
        assert len(order) == 1
        assert order[0].name == "only"

    def test_get_execution_order_chain(self):
        @pipeline("chain")
        def p():
            a = Task("a", add_one)
            b = Task("b", double)
            c = Task("c", add_one)
            a >> b >> c
            return a

        order = p.get_execution_order()
        names = [t.name for t in order]
        assert names.index("a") < names.index("b")
        assert names.index("b") < names.index("c")


# ─────────────────────────── DAGExecutor tests ───────────────────────────────


class TestDAGExecutor:
    def test_run_sync_single_task(self):
        @pipeline("single_exec")
        def p():
            return Task("only", add_one, inputs={"x": 0})

        executor = DAGExecutor()
        result = executor.run_sync(p)
        assert result.status == "success"
        assert result.results["only"] == 1

    def test_run_sync_chain(self):
        @pipeline("chain_exec")
        def p():
            a = Task("a", add_one, inputs={"x": 0})
            b = Task("b", add_one)
            a >> b
            return a

        executor = DAGExecutor()
        result = executor.run_sync(p)
        assert result.status == "success"

    def test_run_sync_with_context(self):
        @pipeline("ctx")
        def p():
            return Task("add", add_one)

        executor = DAGExecutor()
        result = executor.run_sync(p, context={"x": 5})
        assert result.results["add"] == 6

    def test_run_sync_failing_task(self):
        @pipeline("fail_pipeline")
        def p():
            return Task("fail", failing_func)

        executor = DAGExecutor()
        result = executor.run_sync(p)
        assert result.status == "failed"
        assert "fail" in result.errors

    def test_run_sync_returns_pipeline_result(self):
        @pipeline("p_result")
        def p():
            return Task("t", add_one, inputs={"x": 1})

        executor = DAGExecutor()
        result = executor.run_sync(p)
        assert isinstance(result, PipelineResult)

    def test_pipeline_result_has_run_id(self):
        @pipeline("p_id")
        def p():
            return Task("t", add_one, inputs={"x": 1})

        executor = DAGExecutor()
        result = executor.run_sync(p)
        assert result.pipeline_run_id
        assert len(result.pipeline_run_id) > 0

    def test_pipeline_result_duration(self):
        @pipeline("p_dur")
        def p():
            return Task("t", add_one, inputs={"x": 1})

        executor = DAGExecutor()
        result = executor.run_sync(p)
        assert result.duration_seconds >= 0

    def test_dag_executor_with_db_session(self, db_session):
        @pipeline("db_pipe")
        def p():
            return Task("t", add_one, inputs={"x": 1})

        executor = DAGExecutor(db_session=db_session)
        result = executor.run_sync(p)
        assert result.status == "success"

    def test_empty_pipeline(self):
        @pipeline("empty")
        def p():
            return None

        executor = DAGExecutor()
        result = executor.run_sync(p)
        assert result.status == "success"
        assert result.results == {}
