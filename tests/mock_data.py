"""
Mock data generators for ModelTrack tests.
"""

from typing import Any, Dict, List, Optional

import numpy as np
import pandas as pd
from sklearn.datasets import make_classification, make_regression
from sklearn.linear_model import LinearRegression, LogisticRegression
from sklearn.pipeline import Pipeline as SKPipeline
from sklearn.preprocessing import StandardScaler

from modeltrack.models.registry import Model
from modeltrack.shared.utils import generate_id, timestamp_now


# ─────────────────────────── DataFrame generators ────────────────────────────


def make_clean_df(n_rows: int = 100, seed: int = 0) -> pd.DataFrame:
    """Return a clean DataFrame with no nulls or duplicates."""
    rng = np.random.default_rng(seed)
    return pd.DataFrame(
        {
            "id": range(n_rows),
            "feature_1": rng.normal(0, 1, n_rows),
            "feature_2": rng.uniform(0, 100, n_rows),
            "label": rng.integers(0, 2, n_rows),
            "category": [f"cat_{i % 3}" for i in range(n_rows)],
        }
    )


def make_df_with_nulls(
    n_rows: int = 100,
    null_columns: Optional[List[str]] = None,
    null_pct: float = 0.2,
    seed: int = 0,
) -> pd.DataFrame:
    """Return a DataFrame with deliberate null values."""
    df = make_clean_df(n_rows, seed)
    rng = np.random.default_rng(seed + 1)
    null_columns = null_columns or ["feature_1"]
    for col in null_columns:
        null_mask = rng.random(n_rows) < null_pct
        df.loc[null_mask, col] = np.nan
    return df


def make_df_with_outliers(
    n_rows: int = 100,
    outlier_column: str = "feature_1",
    n_outliers: int = 5,
    seed: int = 0,
) -> pd.DataFrame:
    """Return a DataFrame with extreme outlier values."""
    df = make_clean_df(n_rows, seed)
    rng = np.random.default_rng(seed + 2)
    outlier_indices = rng.choice(n_rows, size=n_outliers, replace=False)
    df.loc[outlier_indices, outlier_column] = 1000.0 + rng.normal(0, 10, n_outliers)
    return df


def make_df_with_duplicates(
    n_rows: int = 100,
    n_duplicates: int = 10,
    seed: int = 0,
) -> pd.DataFrame:
    """Return a DataFrame with duplicate rows."""
    df = make_clean_df(n_rows, seed)
    dupes = df.head(n_duplicates).copy()
    return pd.concat([df, dupes], ignore_index=True)


# ─────────────────────────── Model generators ────────────────────────────────


def make_sklearn_classifier(seed: int = 42) -> Any:
    """Return a fitted scikit-learn LogisticRegression."""
    X, y = make_classification(n_samples=200, n_features=10, random_state=seed)
    pipe = SKPipeline(
        [("scaler", StandardScaler()), ("clf", LogisticRegression(random_state=seed))]
    )
    pipe.fit(X, y)
    return pipe


def make_sklearn_regressor(seed: int = 42) -> Any:
    """Return a fitted scikit-learn LinearRegression."""
    X, y = make_regression(n_samples=200, n_features=5, noise=0.1, random_state=seed)
    pipe = SKPipeline(
        [("scaler", StandardScaler()), ("reg", LinearRegression())]
    )
    pipe.fit(X, y)
    return pipe


def make_model(
    name: str = "test_model",
    version: str = "1.0.0",
    stage: str = "dev",
    metrics: Optional[Dict[str, float]] = None,
    hyperparameters: Optional[Dict[str, Any]] = None,
    model_binary: Any = None,
) -> Model:
    """Return a :class:`Model` instance with sensible defaults."""
    if metrics is None:
        metrics = {"accuracy": 0.85, "f1": 0.83, "auc": 0.90}
    if hyperparameters is None:
        hyperparameters = {"n_estimators": 100, "max_depth": 5}
    if model_binary is None:
        model_binary = make_sklearn_classifier()

    return Model(
        name=name,
        version=version,
        model_binary=model_binary,
        metrics=metrics,
        hyperparameters=hyperparameters,
        stage=stage,
        created_at=timestamp_now(),
    )


def make_model_v2(name: str = "test_model") -> Model:
    """Return a second version of a model with slightly better metrics."""
    return make_model(
        name=name,
        version="2.0.0",
        metrics={"accuracy": 0.92, "f1": 0.90, "auc": 0.95},
        hyperparameters={"n_estimators": 200, "max_depth": 8},
        model_binary=make_sklearn_classifier(seed=99),
    )


# ─────────────────────────── A/B test helpers ────────────────────────────────


def make_observations(
    n: int = 50,
    model_key: str = "model_a",
    noise: float = 0.1,
    seed: int = 0,
) -> List[Dict[str, Any]]:
    """Generate synthetic (prediction, actual) observation pairs."""
    rng = np.random.default_rng(seed)
    actuals = rng.normal(0.5, 0.2, n).clip(0, 1)
    predictions = (actuals + rng.normal(0, noise, n)).clip(0, 1)
    return [
        {
            "model_key": model_key,
            "prediction": float(predictions[i]),
            "actual": float(actuals[i]),
            "latency_ms": float(rng.uniform(10, 100)),
        }
        for i in range(n)
    ]
