"""Vercel Python entrypoint for the GeneLink Flask application."""
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
API_SERVER = os.path.join(ROOT, "artifacts", "api-server")

if API_SERVER not in sys.path:
    sys.path.insert(0, API_SERVER)

from app import app  # noqa: E402,F401
