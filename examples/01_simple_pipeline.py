"""Example: Define and run a simple pipeline"""

import pandas as pd
import numpy as np
from modeltrack.pipelines import pipeline, Task
from modeltrack.pipelines.core import DAGExecutor


def read_data():
    """Read sample CSV"""
    return pd.DataFrame(
        {
            "id": range(100),
            "value": np.random.normal(50, 10, 100),
            "category": ["A", "B"] * 50,
        }
    )


def clean_data(df):
    """Remove nulls and duplicates"""
    return df.drop_duplicates().dropna()


def aggregate_data(df):
    """Aggregate by category"""
    return df.groupby("category")["value"].agg(["mean", "std", "count"]).reset_index()


@pipeline("simple_aggregation")
def my_pipeline():
    raw = Task("read", read_data)
    clean = Task("clean", clean_data, inputs=raw)
    agg = Task("aggregate", aggregate_data, inputs=clean)
    return raw >> clean >> agg


if __name__ == "__main__":
    executor = DAGExecutor()
    result = executor.run_sync(my_pipeline)

    print(f"✓ Pipeline completed: {result.status}")
    print(f"Duration: {result.duration_seconds:.2f}s")
    print(result.results)
