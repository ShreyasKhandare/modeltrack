import streamlit as st
from modeltrack.shared.database import get_session
from modeltrack.models.registry import ModelRegistry
from modeltrack.pipelines.storage import PipelineStorage
import pandas as pd
import json


def get_registry():
    """Get model registry instance"""
    return ModelRegistry()


def get_pipeline_storage():
    """Get pipeline storage instance"""
    return PipelineStorage("./pipelines_store")


def format_metrics(metrics: dict) -> str:
    """Format metrics for display"""
    return json.dumps(metrics, indent=2)


def df_to_table(df: pd.DataFrame):
    """Display DataFrame as Streamlit table"""
    st.dataframe(df, use_container_width=True)


def format_timestamp(ts: str) -> str:
    """Format ISO timestamp for display"""
    if not ts:
        return "N/A"
    return ts.split("T")[0] + " " + ts.split("T")[1][:8]
