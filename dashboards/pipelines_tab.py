import streamlit as st
import pandas as pd
from modeltrack.shared.database import get_session
from .utils import (
    get_pipeline_storage,
    format_timestamp,
    df_to_table,
)


def show_pipelines_tab():
    st.header("📊 Pipelines")

    tab1, tab2, tab3 = st.tabs(["Status", "Data Quality", "Lineage"])

    # Tab 1: Pipeline Status
    with tab1:
        st.subheader("Pipeline Runs")

        storage = get_pipeline_storage()
        pipelines = storage.list_pipelines()

        if not pipelines:
            st.info("No pipelines found. Define one using @pipeline decorator.")
        else:
            # Display pipeline list with run button
            for pipeline_info in pipelines:
                col1, col2, col3 = st.columns([3, 1, 1])
                with col1:
                    st.write(f"**{pipeline_info['name']}**")
                with col2:
                    if st.button("Run", key=f"run_{pipeline_info['name']}"):
                        st.success(f"Pipeline {pipeline_info['name']} started")
                with col3:
                    if st.button("History", key=f"hist_{pipeline_info['name']}"):
                        st.info("View execution history")

        # Recent runs
        st.subheader("Recent Runs")
        with get_session() as session:
            from modeltrack.shared.database import PipelineRun

            runs = (
                session.query(PipelineRun)
                .order_by(PipelineRun.started_at.desc())
                .limit(5)
                .all()
            )

            if runs:
                df = pd.DataFrame(
                    [
                        {
                            "Pipeline": r.pipeline_name,
                            "Status": r.status,
                            "Started": format_timestamp(r.started_at),
                            "Duration (s)": (
                                round(
                                    (r.completed_at - r.started_at).total_seconds(), 2
                                )
                                if r.completed_at
                                else "Running"
                            ),
                        }
                        for r in runs
                    ]
                )
                df_to_table(df)
            else:
                st.info("No pipeline runs yet")

    # Tab 2: Data Quality
    with tab2:
        st.subheader("Data Validation Results")
        st.info("Run pipelines to see validation reports")

        # Placeholder for validation metrics
        col1, col2, col3 = st.columns(3)
        with col1:
            st.metric("Valid Records", "1,245 (95%)")
        with col2:
            st.metric("Duplicates Found", "12 (1%)")
        with col3:
            st.metric("Outliers Detected", "43 (3%)")

    # Tab 3: Lineage
    with tab3:
        st.subheader("Data Lineage Visualization")
        st.info("Lineage data will appear after pipeline execution")

        # Placeholder for lineage graph
        st.write("Task → Data flow will be visualized here")


if __name__ == "__main__":
    show_pipelines_tab()
