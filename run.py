#!/usr/bin/env python
"""
Run script for TCF Sermon Searcher.

This script ensures the application starts correctly with proper paths and environment.
"""

import os
import sys
import logging
from dotenv import load_dotenv

# Add the project root to the Python path
sys.path.insert(0, os.path.abspath(os.path.dirname(__file__)))

# Load environment variables from .env file if it exists
load_dotenv()

# Import the application
from sermon_search.app_factory import create_app

# Create the application
app = create_app()

if __name__ == "__main__":
    # Configure logging
    logging.basicConfig(
        level=logging.INFO if not app.debug else logging.DEBUG,
        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
    )
    # Run the server
    app.run(host="0.0.0.0", port=5000, debug=app.config.get('DEBUG', False))