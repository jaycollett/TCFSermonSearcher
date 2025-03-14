"""
Database package for the TCF Sermon Searcher.

This package contains modules for database operations and models.
"""

# Import common database functions to make them available from sermon_search.database
from sermon_search.database.models import (
    get_db,
    init_db,
    query_db,
    get_sermon_by_guid,
    get_ai_content_by_guid
)