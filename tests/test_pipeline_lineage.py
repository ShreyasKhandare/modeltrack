"""
Tests for modeltrack.pipelines.lineage — LineageTracker.
"""

import pytest

from modeltrack.pipelines.lineage import LineageTracker


class TestLineageTracker:
    def test_record_task_start_returns_id(self):
        tracker = LineageTracker(pipeline_run_id="run_1")
        node_id = tracker.record_task_start("load_data", input_data={"file": "x.csv"})
        assert node_id
        assert isinstance(node_id, str)

    def test_record_task_start_creates_node(self):
        tracker = LineageTracker(pipeline_run_id="run_1")
        node_id = tracker.record_task_start("load_data")
        graph = tracker.get_lineage_graph()
        node_ids = [n["id"] for n in graph["nodes"]]
        assert node_id in node_ids

    def test_record_task_end_updates_metadata(self):
        tracker = LineageTracker(pipeline_run_id="run_1")
        node_id = tracker.record_task_start("transform")
        tracker.record_task_end(node_id, output_data={"rows": 100})
        node = tracker._nodes[node_id]
        assert "completed_at" in node["metadata"]

    def test_record_data_node(self):
        tracker = LineageTracker(pipeline_run_id="run_1")
        node_id = tracker.record_data_node("raw_data", data={"key": "value"})
        assert node_id in tracker._nodes
        node = tracker._nodes[node_id]
        assert node["node_type"] == "data"

    def test_add_edge(self):
        tracker = LineageTracker(pipeline_run_id="run_1")
        src = tracker.record_task_start("task_a")
        dst = tracker.record_data_node("output_a")
        tracker.add_edge(src, dst)
        graph = tracker.get_lineage_graph()
        edges = graph["edges"]
        assert any(e["source_id"] == src and e["target_id"] == dst for e in edges)

    def test_get_lineage_graph_structure(self):
        tracker = LineageTracker(pipeline_run_id="run_2")
        tracker.record_task_start("t1")
        tracker.record_data_node("d1")
        graph = tracker.get_lineage_graph()
        assert "nodes" in graph
        assert "edges" in graph
        assert "pipeline_run_id" in graph
        assert len(graph["nodes"]) == 2

    def test_trace_record_basic(self):
        tracker = LineageTracker(pipeline_run_id="run_3")
        n1 = tracker.record_data_node("source")
        n2 = tracker.record_task_start("transform")
        n3 = tracker.record_data_node("output")
        tracker.add_edge(n1, n2)
        tracker.add_edge(n2, n3)
        path = tracker.trace_record("output")
        assert isinstance(path, list)
        assert any(n["id"] == n3 for n in path)

    def test_persistence_with_db_session(self, db_session):
        tracker = LineageTracker(pipeline_run_id="run_db", db_session=db_session)
        node_id = tracker.record_task_start("my_task", input_data=[1, 2, 3])
        tracker.record_task_end(node_id, output_data=[4, 5, 6])
        graph = tracker.get_lineage_graph()
        assert len(graph["nodes"]) >= 1

    def test_unknown_node_end_is_noop(self):
        tracker = LineageTracker(pipeline_run_id="run_1")
        # Should not raise
        tracker.record_task_end("nonexistent_id", output_data=None)
