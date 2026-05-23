"""
Shared pytest fixtures for ModelTrack test suite.
"""

import pytest
import numpy as np
import pandas as pd
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from modeltrack.shared.database import Base, init_db


@pytest.fixture
def db_session():
    """In-memory SQLite session for tests."""
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    Session = sessionmaker(bind=engine)
    session = Session()
    yield session
    session.close()


@pytest.fixture
def temp_dir(tmp_path):
    """Temporary directory as a string path."""
    return str(tmp_path)


@pytest.fixture
def sample_df():
    """A small DataFrame with varied column types for testing."""
    rng = np.random.default_rng(42)
    return pd.DataFrame(
        {
            "id": range(100),
            "value": rng.normal(50, 10, 100),
            "category": ["A", "B"] * 50,
            "timestamp": pd.date_range("2024-01-01", periods=100, freq="h"),
        }
    )
