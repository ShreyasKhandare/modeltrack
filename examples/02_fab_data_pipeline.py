"""Example: Fab sensor data pipeline with validation"""

import pandas as pd
import numpy as np
from modeltrack.pipelines import pipeline, Task
from modeltrack.pipelines.core import DAGExecutor
from modeltrack.pipelines.validators import (
    DataValidator,
    OutlierDetector,
    NullChecker,
)


def read_fab_sensors():
    """Read fab sensor data"""
    df = pd.DataFrame(
        {
            "timestamp": pd.date_range("2024-01-01", periods=1000, freq="1H"),
            "wafer_id": np.random.randint(1000, 2000, 1000),
            "temperature_c": np.random.normal(250, 15, 1000),
            "pressure_pa": np.random.normal(1e5, 5e3, 1000),
            "yield_pct": np.random.uniform(90, 99.5, 1000),
        }
    )
    # Add some anomalies
    df.loc[50:52, "temperature_c"] = 500  # Outliers
    df.loc[100, "yield_pct"] = np.nan  # Null
    return df


def validate_fab_data(df):
    """Validate sensor data"""
    validator = DataValidator()
    validator.add(NullChecker(["yield_pct", "temperature_c"], max_null_pct=0.02))
    validator.add(OutlierDetector(["temperature_c", "pressure_pa"], method="iqr"))
    report = validator.validate(df)
    return df, report  # Return both data and report


def aggregate_by_wafer(data_and_report):
    """Aggregate by wafer"""
    df, report = data_and_report
    print(f"Validation: {report.valid_pct*100:.1f}% valid records")
    return (
        df.groupby("wafer_id")
        .agg(
            {
                "temperature_c": ["mean", "std"],
                "pressure_pa": ["mean", "std"],
                "yield_pct": ["mean", "min", "max"],
            }
        )
        .reset_index()
    )


@pipeline("fab_data_processing")
def fab_pipeline():
    raw = Task("read_sensors", read_fab_sensors)
    validated = Task("validate", validate_fab_data, inputs=raw)
    agg = Task("aggregate", aggregate_by_wafer, inputs=validated)
    return raw >> validated >> agg


if __name__ == "__main__":
    executor = DAGExecutor()
    result = executor.run_sync(fab_pipeline)

    print(f"✓ Fab pipeline completed: {result.status}")
    print(f"Processed {len(result.results['aggregate'])} wafers")
