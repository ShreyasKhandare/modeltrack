FROM python:3.11-slim

WORKDIR /app


COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt


COPY . .

# Expose ports for FastAPI (8080) and Streamlit (8501)
EXPOSE 8080 8501


CMD sh -c "streamlit run dashboards/main.py --server.port 8501 --server.address localhost & sleep 2 && uvicorn modeltrack.api.main:app --host 0.0.0.0 --port 8080"
