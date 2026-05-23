"""
SQLAlchemy database setup and ORM models for ModelTrack.
"""

from contextlib import contextmanager
from datetime import datetime
from typing import Generator, Optional

from sqlalchemy import (
    Boolean,
    DateTime,
    Float,
    ForeignKey,
    String,
    Text,
    create_engine,
)
from sqlalchemy.orm import DeclarativeBase, Mapped, Session, mapped_column, sessionmaker

from modeltrack.shared.logger import get_logger

logger = get_logger(__name__)


# ─────────────────────────── Base ────────────────────────────────────────────


class Base(DeclarativeBase):
    """Declarative base for all ORM models."""


# ─────────────────────────── ORM Models ──────────────────────────────────────


class PipelineRun(Base):
    """Tracks a single execution of a named pipeline."""

    __tablename__ = "pipeline_runs"

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    pipeline_name: Mapped[str] = mapped_column(String(255), nullable=False, index=True)
    status: Mapped[str] = mapped_column(String(32), nullable=False, default="pending")
    started_at: Mapped[datetime] = mapped_column(DateTime, nullable=False)
    completed_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    error: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    metadata_json: Mapped[Optional[str]] = mapped_column(Text, nullable=True)

    def __repr__(self) -> str:
        return f"<PipelineRun id={self.id!r} pipeline={self.pipeline_name!r} status={self.status!r}>"


class TaskRun(Base):
    """Tracks a single task execution within a pipeline run."""

    __tablename__ = "task_runs"

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    pipeline_run_id: Mapped[str] = mapped_column(
        String(64), ForeignKey("pipeline_runs.id"), nullable=False, index=True
    )
    task_name: Mapped[str] = mapped_column(String(255), nullable=False)
    status: Mapped[str] = mapped_column(String(32), nullable=False, default="pending")
    started_at: Mapped[datetime] = mapped_column(DateTime, nullable=False)
    completed_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    inputs_hash: Mapped[Optional[str]] = mapped_column(String(128), nullable=True)
    outputs_hash: Mapped[Optional[str]] = mapped_column(String(128), nullable=True)
    error: Mapped[Optional[str]] = mapped_column(Text, nullable=True)

    def __repr__(self) -> str:
        return (
            f"<TaskRun id={self.id!r} task={self.task_name!r} status={self.status!r}>"
        )


class LineageNode(Base):
    """A node in the data-lineage graph (task or data artifact)."""

    __tablename__ = "lineage_nodes"

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    node_type: Mapped[str] = mapped_column(
        String(32), nullable=False
    )  # "task" | "data"
    pipeline_run_id: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    metadata_json: Mapped[Optional[str]] = mapped_column(Text, nullable=True)

    def __repr__(self) -> str:
        return (
            f"<LineageNode id={self.id!r} name={self.name!r} type={self.node_type!r}>"
        )


class LineageEdge(Base):
    """A directed edge in the data-lineage graph."""

    __tablename__ = "lineage_edges"

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    source_id: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    target_id: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    pipeline_run_id: Mapped[str] = mapped_column(String(64), nullable=False, index=True)

    def __repr__(self) -> str:
        return f"<LineageEdge {self.source_id!r} → {self.target_id!r}>"


class ModelRecord(Base):
    """Persists metadata about a registered model."""

    __tablename__ = "model_records"

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    name: Mapped[str] = mapped_column(String(255), nullable=False, index=True)
    version: Mapped[str] = mapped_column(String(64), nullable=False)
    stage: Mapped[str] = mapped_column(String(32), nullable=False, default="dev")
    model_path: Mapped[str] = mapped_column(String(512), nullable=False)
    metrics_json: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    hyperparams_json: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, nullable=False)
    promoted_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)

    def __repr__(self) -> str:
        return f"<ModelRecord name={self.name!r} version={self.version!r} stage={self.stage!r}>"


class ABTestRecord(Base):
    """Stores the configuration and outcome of an A/B test."""

    __tablename__ = "ab_test_records"

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    test_name: Mapped[str] = mapped_column(String(255), nullable=False)
    model_a: Mapped[str] = mapped_column(String(255), nullable=False)
    model_b: Mapped[str] = mapped_column(String(255), nullable=False)
    traffic_split: Mapped[float] = mapped_column(Float, nullable=False, default=0.1)
    status: Mapped[str] = mapped_column(String(32), nullable=False, default="running")
    winner: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, nullable=False)
    completed_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    results_json: Mapped[Optional[str]] = mapped_column(Text, nullable=True)

    def __repr__(self) -> str:
        return f"<ABTestRecord id={self.id!r} name={self.test_name!r} status={self.status!r}>"


class ABTestObservation(Base):
    """A single prediction / actual observation recorded during an A/B test."""

    __tablename__ = "ab_test_observations"

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    test_id: Mapped[str] = mapped_column(
        String(64), ForeignKey("ab_test_records.id"), nullable=False, index=True
    )
    model_key: Mapped[str] = mapped_column(
        String(16), nullable=False
    )  # "model_a" | "model_b"
    prediction: Mapped[float] = mapped_column(Float, nullable=False)
    actual: Mapped[float] = mapped_column(Float, nullable=False)
    timestamp: Mapped[datetime] = mapped_column(DateTime, nullable=False)
    latency_ms: Mapped[Optional[float]] = mapped_column(Float, nullable=True)

    def __repr__(self) -> str:
        return (
            f"<ABTestObservation test={self.test_id!r} model={self.model_key!r}"
            f" pred={self.prediction} actual={self.actual}>"
        )


# ─────────────────────────── Engine / Session ────────────────────────────────

_engine_cache: dict = {}


def get_engine(db_url: Optional[str] = None):
    """Return (and cache) a SQLAlchemy engine for *db_url*."""
    if db_url is None:
        from modeltrack.config import get_settings

        db_url = get_settings().DATABASE_URL

    if db_url not in _engine_cache:
        connect_args = {}
        if db_url.startswith("sqlite"):
            connect_args["check_same_thread"] = False
        _engine_cache[db_url] = create_engine(db_url, connect_args=connect_args)
        logger.info("Database engine created", extra={"db_url": db_url})

    return _engine_cache[db_url]


def init_db(db_url: Optional[str] = None) -> None:
    """Create all tables if they do not already exist."""
    engine = get_engine(db_url)
    Base.metadata.create_all(engine)
    logger.info("Database tables initialised")


@contextmanager
def get_session(db_url: Optional[str] = None) -> Generator[Session, None, None]:
    """Context manager that yields a SQLAlchemy :class:`Session`."""
    engine = get_engine(db_url)
    _Session = sessionmaker(bind=engine, autoflush=False, autocommit=False)
    session: Session = _Session()
    try:
        yield session
        session.commit()
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()
