import streamlit as st
import pandas as pd
import plotly.graph_objects as go
import json
from modeltrack.models.registry import ModelRegistry
from modeltrack.shared.database import get_session, ModelRecord, ABTestRecord
from .utils import *


def show_models_tab():
    st.header("🤖 Models")

    tab1, tab2, tab3 = st.tabs(["Registry", "A/B Tests", "Retraining"])

    # Tab 1: Model Registry
    with tab1:
        st.subheader("Model Registry")

        registry = get_registry()

        with get_session() as session:
            models = session.query(ModelRecord).all()

            if not models:
                st.info("No models registered yet")
            else:
                # Group by model name
                for model_name in set(m.name for m in models):
                    with st.expander(f"📦 {model_name}"):
                        model_versions = [m for m in models if m.name == model_name]

                        df = pd.DataFrame(
                            [
                                {
                                    "Version": m.version,
                                    "Stage": m.stage,
                                    "Created": format_timestamp(m.created_at),
                                    "Metrics": format_metrics(
                                        json.loads(m.metrics_json)
                                    ),
                                }
                                for m in sorted(
                                    model_versions,
                                    key=lambda x: x.created_at,
                                    reverse=True,
                                )
                            ]
                        )
                        df_to_table(df)

                        # Promote button
                        prod = next(
                            (m for m in model_versions if m.stage == "production"),
                            None,
                        )
                        if prod:
                            st.write(f"**Production:** v{prod.version}")

    # Tab 2: A/B Tests
    with tab2:
        st.subheader("A/B Test Results")

        with get_session() as session:
            tests = (
                session.query(ABTestRecord)
                .order_by(ABTestRecord.created_at.desc())
                .all()
            )

            if not tests:
                st.info("No A/B tests run yet")
            else:
                for test in tests:
                    with st.expander(f"🧪 {test.test_name}"):
                        results = json.loads(test.results_json)

                        col1, col2, col3 = st.columns(3)
                        with col1:
                            st.metric("Status", test.status)
                        with col2:
                            st.metric("Winner", test.winner or "TBD")
                        with col3:
                            st.metric(
                                "Observations", len(results.get("observations", []))
                            )

                        st.write(f"**Model A:** {test.model_a}")
                        st.write(f"**Model B:** {test.model_b}")
                        st.write(f"**Traffic Split:** {test.traffic_split * 100}%")

    # Tab 3: Retraining
    with tab3:
        st.subheader("Model Retraining History")
        st.info("Retraining jobs will appear after configuration")

        col1, col2 = st.columns(2)
        with col1:
            st.write("**Scheduled Jobs**")
            st.info("No scheduled retraining jobs")
        with col2:
            st.write("**Recent Retrains**")
            st.info("No recent retraining runs")


if __name__ == "__main__":
    show_models_tab()
