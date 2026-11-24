"""Vercel entrypoint for the existing GeneLink Flask application.

The application itself remains in artifacts/api-server/app.py; this small
adapter exposes its WSGI object at the repository root so Vercel can detect
Flask automatically without changing the existing URL structure.
"""
import importlib.util
import sys
from pathlib import Path

BACKEND_APP = Path(__file__).resolve().parent / "artifacts" / "api-server" / "app.py"
MODULE_NAME = "_genelink_backend_app"

spec = importlib.util.spec_from_file_location(MODULE_NAME, BACKEND_APP)
if spec is None or spec.loader is None:
    raise RuntimeError("Could not load GeneLink Flask application")

backend = importlib.util.module_from_spec(spec)
sys.modules[MODULE_NAME] = backend
spec.loader.exec_module(backend)

app = backend.app
