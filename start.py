"""Container startup: initialize DB then launch uvicorn."""

import os
import subprocess
import sys

from modeltrack.shared.database import init_db
from modeltrack.config import get_settings
from pathlib import Path

settings = get_settings()

Path(settings.MODELS_DIR).mkdir(exist_ok=True, parents=True)
Path(settings.PIPELINES_DIR).mkdir(exist_ok=True, parents=True)
init_db()
print("✓ Database initialized", flush=True)

port = int(os.environ.get("PORT", 8000))
print(f"✓ Starting API on port {port}", flush=True)

subprocess.run(
    [
        sys.executable, "-m", "uvicorn",
        "modeltrack.api.main:app",
        "--host", "0.0.0.0",
        "--port", str(port),
    ],
    check=True,
)
