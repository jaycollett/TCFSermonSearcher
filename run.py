#!/usr/bin/env python
"""
Run script for TCF Sermon Searcher (wrapper).

This is a wrapper script that imports and executes the actual run script
from the sermon_search package.
"""

if __name__ == "__main__":
    from sermon_search.run import app
    app.run(host="0.0.0.0", port=5000, debug=app.config.get('DEBUG', False))