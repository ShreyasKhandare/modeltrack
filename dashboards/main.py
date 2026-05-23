import streamlit as st
from .pipelines_tab import show_pipelines_tab
from .models_tab import show_models_tab
from modeltrack.config import get_settings

st.set_page_config(
    page_title="ModelTrack",
    page_icon="🚀",
    layout="wide",
    initial_sidebar_state="expanded",
)

st.title("🚀 ModelTrack")
st.write("Unified data pipeline + model registry framework")

# Sidebar
with st.sidebar:
    st.header("Navigation")
    page = st.radio("Select View", ["Pipelines", "Models", "Settings"])

    st.divider()

    st.subheader("Info")
    st.write("**Version:** 0.1.0")
    st.write("**Status:** Running")

    st.divider()

    st.subheader("Quick Links")
    st.markdown("""
    - [API Docs](/docs)
    - [GitHub](https://github.com/ShreyasKhandare/modeltrack)
    - [Issues](https://github.com/ShreyasKhandare/modeltrack/issues)
    """)

# Main content
if page == "Pipelines":
    show_pipelines_tab()
elif page == "Models":
    show_models_tab()
else:  # Settings
    st.header("⚙️ Settings")

    settings = get_settings()
    st.write(f"**Database:** {settings.DATABASE_URL}")
    st.write(f"**API Host:** {settings.API_HOST}:{settings.API_PORT}")
    st.write(f"**Log Level:** {settings.LOG_LEVEL}")
    st.write(f"**Models Directory:** {settings.MODELS_DIR}")
    st.write(f"**Pipelines Directory:** {settings.PIPELINES_DIR}")

st.divider()
st.caption("ModelTrack © 2024 - Built for production ML pipelines")
