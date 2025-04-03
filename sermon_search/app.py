"""
Main entry point for the TCF Sermon Searcher application.

This module provides WSGI compatibility for the Flask application.
For running the application directly, use run.py instead.
"""

import os

# Create the Flask application
from sermon_search.app_factory import create_app
app = create_app(os.getenv('FLASK_ENV', 'development'))

# This file is used by gunicorn in production:
# gunicorn --bind 0.0.0.0:5000 sermon_search.app:app