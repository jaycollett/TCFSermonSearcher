"""
Routes module for the TCF Sermon Searcher application.

This module defines all route handlers for the web application.
"""

import os
import re
import json
import math
import uuid
import datetime
import logging
import nltk
from collections import Counter
from typing import Dict, Any, List, Union, Optional

from flask import (
    Blueprint, current_app, render_template, request, redirect, 
    url_for, make_response, jsonify, send_from_directory
)
from flask_babel import gettext as _
from nltk.corpus import stopwords

# For headless chart generation
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from wordcloud import WordCloud, STOPWORDS

# Local imports
from sermon_search.database import get_db, get_sermon_by_guid, get_ai_content_by_guid
from sermon_search.utils import (
    get_client_ip,
    is_ip_banned,
    verify_api_token,
    get_all_categories,
    extract_relevant_snippets,
    format_text_into_paragraphs,
    highlight_search_terms,
    sanitize_search_term,
    extract_first_sentences,
    search_sermons,
    get_sermon_statistics
)

# Ensure NLTK resources are available
nltk.download('stopwords', quiet=True)

# Create a blueprint for routes
bp = Blueprint("main", __name__)


# --- Route Handlers ---

@bp.route("/")
def index():
    """Render the application homepage."""
    greeting = _("Welcome to Sermon Search!")
    return render_template("index.html", greeting=greeting)


@bp.route("/set_language", methods=["POST"])
def set_language():
    """
    Set the user's preferred language via a cookie.
    
    Returns:
        Redirect to the homepage with the new language set
    """
    selected_lang = request.form.get("language")
    current_app.logger.info(f"Setting language to: {selected_lang}, Form data: {request.form}")
    
    if selected_lang not in ["en", "es"]:
        selected_lang = "en"
        
    # Create response with redirect
    resp = make_response(redirect(url_for("main.index")))
    
    # Set cookie with language preference
    resp.set_cookie(
        key="language",
        value=selected_lang,
        max_age=365*24*60*60,  # 1 year
        httponly=True,
        path="/"  # Make sure cookie is available for all paths
    )
    
    current_app.logger.info(f"Language set to {selected_lang}, redirecting to {url_for('main.index')}")
    return resp


@bp.route('/sitemap.xml')
def sitemap():
    """Generate a sitemap for search engines."""
    sitemap_xml = """<?xml version="1.0" encoding="UTF-8"?>
                <urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">
                <url>
                    <loc>https://sermonsearch.collett.us/</loc>
                    <priority>1.0</priority>
                </url>
                </urlset>
                """
    return sitemap_xml, 200, {'Content-Type': 'application/xml'}


@bp.route('/Robots.txt')
@bp.route('/robots.txt')
def robots():
    """Generate robots.txt for search engines."""
    robots_txt = """User-agent: *
            Disallow: /
            Allow: /$
            Sitemap: https://sermonsearch.collett.us/sitemap.xml
            """
    return robots_txt, 200, {'Content-Type': 'text/plain'}


@bp.route("/search", methods=["GET"])
def search():
    """
    Handle sermon search requests.
    
    Returns:
        Rendered search template with results if a query was provided
    """
    query = request.args.get("q", "").strip()
    language = request.cookies.get("language", "en")
    selected_categories = request.args.getlist("categories")
    all_categories = get_all_categories(language)

    if not query:
        return render_template(
            "search.html", 
            all_categories=all_categories, 
            selected_categories=selected_categories
        )

    try:
        page = int(request.args.get("page", 1))
        if page < 1:
            page = 1
    except ValueError:
        page = 1

    try:
        # Get search results
        search_results = search_sermons(
            query=query,
            language=language,
            selected_categories=selected_categories,
            page=page,
            per_page=10
        )
        
        sermons = search_results['sermons']
        total_count = search_results['total_count']
        total_pages = math.ceil(total_count / 10) if total_count > 0 else 1
        
        # Process results to extract snippets
        results = []
        for sermon in sermons:
            snippets = extract_relevant_snippets(sermon["transcription"], query)
            if not snippets or snippets == ["(No exact match found)"]:
                snippets = [sermon["transcription"][:200]]
            results.append({
                "sermon_guid": sermon["sermon_guid"],
                "sermon_title": sermon["sermon_title"],
                "audiofilename": sermon["audiofilename"],
                "categories": sermon["categories"],
                "snippets": snippets
            })

    except Exception as e:
        current_app.logger.error(f"Error during search: {str(e)}", exc_info=True)
        return render_template(
            "error.html", 
            message=_("An error occurred while processing your search. Please try again.")
        )

    return render_template(
        "results.html", 
        query=query, 
        results=results,
        highlight_search_terms=highlight_search_terms,
        all_categories=all_categories,
        selected_categories=selected_categories,
        page=page,
        total_pages=total_pages,
        total_count=total_count
    )


@bp.route("/sermon/<sermon_guid>")
def sermon_detail(sermon_guid):
    """
    Display details for a specific sermon.
    
    Args:
        sermon_guid: The unique identifier for the sermon
        
    Returns:
        Rendered sermon detail template
    """
    language = request.cookies.get("language", "en")
    query = request.args.get("q", "").strip()
    selected_categories = request.args.getlist("categories")
    page = request.args.get("page", 1)
    
    sermon = get_sermon_by_guid(sermon_guid, language)
    if not sermon:
        return _("Sermon not found"), 404

    ai_content = get_ai_content_by_guid(sermon_guid)

    formatted_transcript = format_text_into_paragraphs(sermon["transcription"])
    highlighted_transcript = highlight_search_terms(formatted_transcript, query)

    # Process AI-generated quotes if available
    if ai_content and ai_content["key_quotes"]:
        ai_quotes = ai_content["key_quotes"].split(" | ")
        paragraphs = highlighted_transcript.split("</p>")
        for quote in ai_quotes:
            clean_quote = quote.strip().strip('"')
            for i, paragraph in enumerate(paragraphs):
                if clean_quote in paragraph:
                    quote_html = f'<div class="pull-quote">{clean_quote}</div>'
                    paragraphs[i] = paragraph.replace(clean_quote, quote_html)
                    break
        highlighted_transcript = "</p>".join(paragraphs)

    return render_template(
        "sermon.html",
        sermon=sermon,
        ai_content=ai_content,
        language=language,
        formatted_transcript=highlighted_transcript,
        query=query,
        selected_categories=selected_categories,
        page=page
    )


@bp.route("/stats")
def stats():
    """Display statistics about the sermon database."""
    statistics = get_sermon_statistics()
    return render_template("stats.html", **statistics)


@bp.route("/sermons")
def sermon_index():
    """Display an index of available sermons."""
    db = get_db()
    language = request.cookies.get("language", "en")
    cur = db.execute(
        "SELECT sermon_guid, sermon_title, audiofilename, transcription, categories "
        "FROM sermons WHERE language = ? ORDER BY sermon_title ASC LIMIT 12", 
        (language,)
    )
    sermons = cur.fetchall()

    processed_sermons = []
    for sermon in sermons:
        processed_sermons.append({
            "sermon_guid": sermon["sermon_guid"],
            "sermon_title": sermon["sermon_title"],
            "audiofilename": sermon["audiofilename"],
            "snippet": extract_first_sentences(sermon["transcription"]),
            "categories": sermon["categories"] or "Uncategorized"
        })
    return render_template("sermons.html", sermons=processed_sermons)


# API redirect route - for backward compatibility
@bp.route("/api/sermons")
def api_sermons_redirect():
    """
    Redirect to the API endpoint for retrieving sermon list.
    
    This maintains backwards compatibility with existing API clients.
    """
    # Import here to avoid circular imports
    from sermon_search.api.routes import get_sermons
    return get_sermons()


@bp.route("/audiofiles/<path:filename>")
def audiofiles(filename):
    """
    Serve audio files from the configured directory.
    
    Args:
        filename: Path to the audio file
        
    Returns:
        Audio file response
    """
    return send_from_directory(current_app.config.get("AUDIOFILES_DIR"), filename)


# API redirect route - for backward compatibility
@bp.route("/api/update_stats", methods=["POST"])
def update_stats_redirect():
    """
    Redirect to the API endpoint for updating sermon statistics.
    
    This maintains backwards compatibility with existing API clients.
    """
    # Import here to avoid circular imports
    from sermon_search.api.routes import update_stats
    return update_stats()


# API redirect route - for backward compatibility
@bp.route("/api/ai_sermon_content", methods=["POST"])
def upload_ai_sermon_content_redirect():
    """
    Redirect to the API endpoint for uploading AI-generated sermon content.
    
    This maintains backwards compatibility with existing API clients.
    """
    # Import here to avoid circular imports
    from sermon_search.api.routes import upload_ai_sermon_content
    return upload_ai_sermon_content()


# Support both API and UI routes for sermon upload
@bp.route("/upload_sermon", methods=["POST"])
@bp.route("/api/upload_sermon", methods=["POST"])
def upload_sermon_redirect():
    """
    Redirect to the API endpoint for uploading sermons.
    
    This maintains backwards compatibility with existing API clients.
    """
    # Import here to avoid circular imports
    from sermon_search.api.routes import upload_sermon
    return upload_sermon()