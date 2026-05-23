#!/usr/bin/env python
"""Initialize database on container startup."""

from modeltrack.shared.database import init_db
from modeltrack.config import get_settings
from pathlib import Path

settings = get_settings()

# Ensure directories exist
Path(settings.MODELS_DIR).mkdir(exist_ok=True, parents=True)
Path(settings.PIPELINES_DIR).mkdir(exist_ok=True, parents=True)

# Initialize database
init_db()

print("✓ Database initialized")
print(f"  Models dir: {settings.MODELS_DIR}")
print(f"  Pipelines dir: {settings.PIPELINES_DIR}")
print(f"  Database: {settings.DATABASE_URL}")
