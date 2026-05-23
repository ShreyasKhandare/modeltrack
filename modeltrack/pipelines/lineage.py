"""
Data lineage tracking for ModelTrack pipelines.
"""

import json
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from modeltrack.shared.logger import get_logger
from modeltrack.shared.utils import compute_hash, generate_id, safe_json_dumps

logger = get_logger(__name__)


class LineageTracker:
    """
    Tracks data lineage for a single pipeline run.

    Nodes represent tasks or data artifacts; edges represent
    data-flow between them.  All information is persisted to the
    database (when a session is available) and held in memory so that
    callers can query the graph without a DB round-trip.
    """

    def __init__(self, pipeline_run_id: str, db_session=None):
        self.pipeline_run_id = pipeline_run_id
        self._session = db_session

        # In-memory graph
        self._nodes: Dict[str, dict] = {}  # node_id -> node_dict
        self._edges: List[dict] = []       # list of {id, source_id, target_id}

    # ── node recording ───────────────────────────────────────────────────────

    def record_task_start(self, task_name: str, input_data: Any = None) -> str:
        """
        Register the start of *task_name* as a lineage node.

        Returns the newly created node ID.
        """
        node_id = generate_id()
        meta: dict = {
            "started_at": datetime.now(timezone.utc).isoformat(),
            "input_hash": self._hash_data(input_data),
        }
        self._add_node(node_id, name=task_name, node_type="task", metadata=meta)
        return node_id

    def record_task_end(self, task_node_id: str, output_data: Any = None) -> None:
        """Update the lineage node for *task_node_id* with completion info."""
        node = self._nodes.get(task_node_id)
        if node is None:
            logger.warning(
                "record_task_end: node not found",
                extra={"node_id": task_node_id},
            )
            return

        existing_meta = node.get("metadata", {})
        existing_meta["completed_at"] = datetime.now(timezone.utc).isoformat()
        existing_meta["output_hash"] = self._hash_data(output_data)
        node["metadata"] = existing_meta

        # Update in DB
        self._update_node_in_db(task_node_id, existing_meta)

    def record_data_node(self, name: str, data: Any = None) -> str:
        """
        Register a data artifact as a lineage node.

        Returns the newly created node ID.
        """
        node_id = generate_id()
        meta: dict = {
            "recorded_at": datetime.now(timezone.utc).isoformat(),
            "data_hash": self._hash_data(data),
            "data_type": type(data).__name__,
        }
        self._add_node(node_id, name=name, node_type="data", metadata=meta)
        return node_id

    # ── edge recording ───────────────────────────────────────────────────────

    def add_edge(self, source_id: str, target_id: str) -> None:
        """Add a directed edge from *source_id* to *target_id*."""
        edge_id = generate_id()
        edge = {
            "id": edge_id,
            "source_id": source_id,
            "target_id": target_id,
            "pipeline_run_id": self.pipeline_run_id,
        }
        self._edges.append(edge)
        self._persist_edge(edge)

    # ── graph queries ────────────────────────────────────────────────────────

    def get_lineage_graph(self) -> dict:
        """
        Return the full lineage graph as a dictionary with ``nodes`` and ``edges``
        lists.
        """
        return {
            "pipeline_run_id": self.pipeline_run_id,
            "nodes": list(self._nodes.values()),
            "edges": self._edges,
        }

    def trace_record(self, record_id: str) -> List[dict]:
        """
        Trace the ancestry of *record_id* through the lineage graph.

        Performs a reverse BFS from nodes whose name contains *record_id*,
        returning each ancestor node in order.
        """
        # Find matching start nodes
        start_nodes = [
            nid for nid, node in self._nodes.items()
            if record_id in node.get("name", "") or record_id == nid
        ]

        if not start_nodes:
            return []

        # Build reverse adjacency
        reverse_adj: Dict[str, List[str]] = {}
        for edge in self._edges:
            tgt = edge["target_id"]
            src = edge["source_id"]
            reverse_adj.setdefault(tgt, []).append(src)

        # BFS
        visited: set = set()
        queue = list(start_nodes)
        path: List[dict] = []

        while queue:
            nid = queue.pop(0)
            if nid in visited:
                continue
            visited.add(nid)
            node = self._nodes.get(nid)
            if node:
                path.append(node)
            for parent_id in reverse_adj.get(nid, []):
                if parent_id not in visited:
                    queue.append(parent_id)

        return path

    # ── private helpers ──────────────────────────────────────────────────────

    def _add_node(
        self,
        node_id: str,
        name: str,
        node_type: str,
        metadata: Optional[dict] = None,
    ) -> None:
        metadata = metadata or {}
        node = {
            "id": node_id,
            "name": name,
            "node_type": node_type,
            "pipeline_run_id": self.pipeline_run_id,
            "metadata": metadata,
        }
        self._nodes[node_id] = node
        self._persist_node(node)

    @staticmethod
    def _hash_data(data: Any) -> Optional[str]:
        if data is None:
            return None
        try:
            serialised = safe_json_dumps(data).encode()
            return compute_hash(serialised)
        except Exception:
            try:
                return compute_hash(str(data).encode())
            except Exception:
                return None

    def _persist_node(self, node: dict) -> None:
        if self._session is None:
            return
        try:
            from modeltrack.shared.database import LineageNode

            record = LineageNode(
                id=node["id"],
                name=node["name"],
                node_type=node["node_type"],
                pipeline_run_id=node["pipeline_run_id"],
                metadata_json=safe_json_dumps(node.get("metadata", {})),
            )
            self._session.add(record)
            self._session.commit()
        except Exception as exc:
            logger.warning("DB write failed (lineage node)", extra={"error": str(exc)})

    def _update_node_in_db(self, node_id: str, metadata: dict) -> None:
        if self._session is None:
            return
        try:
            from modeltrack.shared.database import LineageNode

            record = self._session.get(LineageNode, node_id)
            if record:
                record.metadata_json = safe_json_dumps(metadata)
                self._session.commit()
        except Exception as exc:
            logger.warning("DB write failed (lineage node update)", extra={"error": str(exc)})

    def _persist_edge(self, edge: dict) -> None:
        if self._session is None:
            return
        try:
            from modeltrack.shared.database import LineageEdge

            record = LineageEdge(
                id=edge["id"],
                source_id=edge["source_id"],
                target_id=edge["target_id"],
                pipeline_run_id=edge["pipeline_run_id"],
            )
            self._session.add(record)
            self._session.commit()
        except Exception as exc:
            logger.warning("DB write failed (lineage edge)", extra={"error": str(exc)})
