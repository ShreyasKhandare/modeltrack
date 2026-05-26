FROM python:3.11-slim

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

EXPOSE 8080

# Run only FastAPI on 8080 (Streamlit will be embedded/called from FastAPI)
CMD ["uvicorn", "modeltrack.api.main:app", "--host", "0.0.0.0", "--port", "8080"]
