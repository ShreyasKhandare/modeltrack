"""
ModelTrack REST API module.

Exports:
  - create_app: FastAPI application factory
  - APIConfig: API configuration class
"""

from .main import create_app
from ..config import Settings as APIConfig

__all__ = ["create_app", "APIConfig"]
