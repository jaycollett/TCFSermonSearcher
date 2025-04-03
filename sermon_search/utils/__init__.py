"""
Utility modules for the TCF Sermon Searcher.

This package contains utility functions used across the application.
"""

# Import common utils to make them available from sermon_search.utils
from sermon_search.utils.text import (
    extract_relevant_snippets, 
    format_text_into_paragraphs,
    highlight_search_terms, 
    sanitize_search_term,
    extract_first_sentences
)

from sermon_search.utils.security import (
    get_client_ip,
    is_ip_banned,
    verify_api_token,
    get_or_create_visitor_id,
    set_visitor_id_cookie
)

from sermon_search.utils.sermons import (
    get_all_categories,
    search_sermons,
    get_sermon_statistics
)