FROM python:3.11-slim

WORKDIR /app

# Install dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy code
COPY . .

# Expose ports
EXPOSE 8000 8501

# Health check
HEALTHCHECK --interval=30s --timeout=5s --start-period=60s --retries=3 \
  CMD python -c "import requests; requests.get('http://localhost:${PORT:-8000}/health')" || exit 1

# Initialize database and run API
CMD ["sh", "-c", "python init_db.py && uvicorn modeltrack.api.main:app --host 0.0.0.0 --port ${PORT:-8000}"]
