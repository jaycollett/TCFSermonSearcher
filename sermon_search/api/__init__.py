"""
API package for the TCF Sermon Searcher.

This package contains API-related modules and endpoints.
"""

from flask import Blueprint

# Create a blueprint for API routes
bp = Blueprint("api", __name__, url_prefix="/api")