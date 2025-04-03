"""
Main entry point for the TCF Sermon Searcher application (wrapper).

This is a wrapper that imports the actual app from the sermon_search package.
"""

from sermon_search.app import app

# This file is used by gunicorn in production:
# gunicorn --bind 0.0.0.0:5000 app:app