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
from sermon_search.database.init_metrics_db import get_metrics_db
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
    get_sermon_statistics,
    get_or_create_visitor_id,
    set_visitor_id_cookie
)

# Ensure NLTK resources are available
nltk.download('stopwords', quiet=True)

# Create a blueprint for routes
bp = Blueprint("main", __name__)


# --- Metrics Tracking Functions ---

def get_search_metrics(days: int = 30, limit: int = 100) -> dict:
    """
    Get recent search metrics data.
    
    Args:
        days: Number of days to look back
        limit: Maximum number of results to return
        
    Returns:
        Dictionary with metrics data
    """
    try:
        db = get_metrics_db()
        
        # Calculate the date range
        date_cutoff = (datetime.datetime.now() - datetime.timedelta(days=days)).strftime('%Y-%m-%d %H:%M:%S')
        
        # Get recent searches
        recent_searches = db.execute(
            "SELECT search_query, category_filters, search_type, ip, timestamp FROM Search_History "
            "WHERE timestamp > ? ORDER BY timestamp DESC LIMIT ?",
            (date_cutoff, limit)
        ).fetchall()
        
        # Get popular searches by search type
        popular_searches = db.execute(
            "SELECT search_query, COUNT(*) as count FROM Search_History "
            "WHERE timestamp > ? GROUP BY search_query ORDER BY count DESC LIMIT 10",
            (date_cutoff,)
        ).fetchall()
        
        # Get search metrics by type
        search_by_type = db.execute(
            "SELECT search_type, COUNT(*) as count FROM Search_History "
            "WHERE timestamp > ? GROUP BY search_type ORDER BY count DESC",
            (date_cutoff,)
        ).fetchall()
        
        # Get popular categories
        popular_categories = db.execute(
            "SELECT category_filters, COUNT(*) as count FROM Search_History "
            "WHERE timestamp > ? AND category_filters IS NOT NULL "
            "GROUP BY category_filters ORDER BY count DESC LIMIT 10",
            (date_cutoff,)
        ).fetchall()
        
        # Get recent sermon accesses
        recent_accesses = db.execute(
            "SELECT sa.sermon_guid, s.sermon_title, sa.ip, sa.timestamp "
            "FROM Sermon_Access sa LEFT JOIN sermons s ON sa.sermon_guid = s.sermon_guid "
            "WHERE sa.timestamp > ? ORDER BY sa.timestamp DESC LIMIT ?",
            (date_cutoff, limit)
        ).fetchall()
        
        # Get popular sermons
        popular_sermons = db.execute(
            "SELECT sa.sermon_guid, s.sermon_title, COUNT(*) as count "
            "FROM Sermon_Access sa LEFT JOIN sermons s ON sa.sermon_guid = s.sermon_guid "
            "WHERE sa.timestamp > ? GROUP BY sa.sermon_guid ORDER BY count DESC LIMIT 10",
            (date_cutoff,)
        ).fetchall()
        
        return {
            "recent_searches": [dict(row) for row in recent_searches],
            "popular_searches": [dict(row) for row in popular_searches],
            "search_by_type": [dict(row) for row in search_by_type],
            "popular_categories": [dict(row) for row in popular_categories],
            "recent_accesses": [dict(row) for row in recent_accesses],
            "popular_sermons": [dict(row) for row in popular_sermons]
        }
    except Exception as e:
        current_app.logger.error(f"Failed to get search metrics: {str(e)}", exc_info=True)
        return {
            "error": str(e),
            "recent_searches": [],
            "popular_searches": [],
            "search_by_type": [],
            "popular_categories": [],
            "recent_accesses": [],
            "popular_sermons": []
        }

def log_search_metrics(query: str, categories: list = None, search_type: str = "new_search") -> None:
    """
    Log search query metrics to the metrics database.
    Implements rate limiting to prevent spamming the database with
    identical searches from the same visitor within a short time window.
    
    Args:
        query: The search query entered by the user
        categories: Optional list of category filters applied
        search_type: Type of search action ('new_search', 'filter_change', etc.)
    """
    # Skip logging in test mode
    if current_app.config.get('TESTING', False):
        return
        
    try:
        db = get_metrics_db()
        ip_address = get_client_ip()
        visitor_id = get_or_create_visitor_id()
        
        # Convert categories list to string if provided
        category_filters = None
        if categories and len(categories) > 0:
            category_filters = ",".join(categories)
        
        # Check for duplicate searches within a time window (1 minute)
        # Only for the same query, categories and type from the same visitor
        one_minute_ago = (datetime.datetime.now() - datetime.timedelta(minutes=1)).strftime('%Y-%m-%d %H:%M:%S')
        cursor = db.execute(
            "SELECT COUNT(*) as count FROM Search_History "
            "WHERE search_query = ? AND visitor_id = ? AND "
            "(category_filters = ? OR (category_filters IS NULL AND ? IS NULL)) "
            "AND search_type = ? AND timestamp > ?",
            (query, visitor_id, category_filters, category_filters, search_type, one_minute_ago)
        )
        recent_search_count = cursor.fetchone()["count"]
        
        # Only log if this is not a duplicate search within the time window
        if recent_search_count == 0:
            db.execute(
                "INSERT INTO Search_History (search_query, ip, visitor_id, category_filters, search_type) VALUES (?, ?, ?, ?, ?)",
                (query, ip_address, visitor_id, category_filters, search_type)
            )
            db.commit()
            current_app.logger.debug(f"Logged {search_type} query: '{query}' with categories: {category_filters} from visitor: {visitor_id}")
        else:
            current_app.logger.debug(f"Skipped logging duplicate search: '{query}' from visitor: {visitor_id} (duplicate within 1-minute window)")
    except Exception as e:
        current_app.logger.error(f"Failed to log search metrics: {str(e)}", exc_info=True)


def log_sermon_access(sermon_guid: str) -> None:
    """
    Log sermon access to the metrics database.
    Only records one access per visitor per sermon per hour to prevent
    duplicate entries from page refreshes.
    
    Args:
        sermon_guid: The unique identifier of the accessed sermon
    """
    # Skip logging in test mode
    if current_app.config.get('TESTING', False):
        return
        
    try:
        db = get_metrics_db()
        ip_address = get_client_ip()
        visitor_id = get_or_create_visitor_id()
        
        # Check if this visitor has accessed this sermon recently (within the last hour)
        one_hour_ago = (datetime.datetime.now() - datetime.timedelta(hours=1)).strftime('%Y-%m-%d %H:%M:%S')
        cursor = db.execute(
            "SELECT COUNT(*) as count FROM Sermon_Access "
            "WHERE sermon_guid = ? AND visitor_id = ? AND timestamp > ?",
            (sermon_guid, visitor_id, one_hour_ago)
        )
        recent_access_count = cursor.fetchone()["count"]
        
        # Only log if this is a new access (not a refresh within the time window)
        if recent_access_count == 0:
            db.execute(
                "INSERT INTO Sermon_Access (sermon_guid, ip, visitor_id) VALUES (?, ?, ?)",
                (sermon_guid, ip_address, visitor_id)
            )
            db.commit()
            current_app.logger.debug(f"Logged sermon access: {sermon_guid} from visitor: {visitor_id}")
        else:
            current_app.logger.debug(f"Skipped logging duplicate sermon access: {sermon_guid} from visitor: {visitor_id}")
    except Exception as e:
        current_app.logger.error(f"Failed to log sermon access: {str(e)}", exc_info=True)


# --- Route Handlers ---

@bp.route("/")
def index():
    """Render the application homepage."""
    greeting = _("Welcome to Sermon Search!")
    response = make_response(render_template("index.html", greeting=greeting))
    
    # When testing, we might not have all functions available
    if current_app.config.get('TESTING', False):
        return response
        
    # Set visitor ID cookie
    return set_visitor_id_cookie(response)


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
    search_type = request.args.get("search_type", "new_search").strip()
    
    if not query:
        response = make_response(render_template(
            "search.html",
            all_categories=all_categories,
            selected_categories=selected_categories
        ))
        
        if current_app.config.get('TESTING', False):
            return response
            
        return set_visitor_id_cookie(response)
    
    # Determine search type if not explicitly provided
    if search_type == "new_search" and "prev_categories" in request.args:
        # Check if categories changed from previous search
        prev_categories = request.args.getlist("prev_categories")
        prev_set = set(prev_categories)
        current_set = set(selected_categories)
        
        if prev_set != current_set:
            search_type = "filter_change"
    
    # Log search metrics
    log_search_metrics(query, selected_categories, search_type)
    try:
        page = int(request.args.get("page", 1))
        if page < 1:
            page = 1
    except ValueError:
        page = 1
    try:
        search_results = search_sermons(
            query=query,
            language=language,
            selected_categories=selected_categories,
            page=page,
            per_page=10
        )
        sermons = search_results["sermons"]
        total_count = search_results["total_count"]
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
        total_pages = math.ceil(total_count / 10)
    except Exception as e:
        current_app.logger.error(f"Error during search: {str(e)}", exc_info=True)
        return render_template(
            "error.html",
            message=_("An error occurred while processing your search. Please try again.")
        )
    response = make_response(render_template(
        "results.html",
        query=query,
        results=results,
        highlight_search_terms=highlight_search_terms,
        all_categories=all_categories,
        selected_categories=selected_categories,
        page=page,
        total_pages=total_pages,
        total_count=total_count
    ))
    
    if current_app.config.get('TESTING', False):
        return response
        
    return set_visitor_id_cookie(response)


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
    
    # Log sermon access
    log_sermon_access(sermon_guid)

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

    response = make_response(render_template(
        "sermon.html",
        sermon=sermon,
        ai_content=ai_content,
        language=language,
        formatted_transcript=highlighted_transcript,
        query=query,
        selected_categories=selected_categories,
        page=page
    ))
    
    if current_app.config.get('TESTING', False):
        return response
        
    return set_visitor_id_cookie(response)


@bp.route("/stats")
def stats():
    """Display statistics about the sermon database."""
    statistics = get_sermon_statistics()
    response = make_response(render_template("stats.html", **statistics))
    
    if current_app.config.get('TESTING', False):
        return response
        
    return set_visitor_id_cookie(response)


@bp.route("/sermons")
def sermon_index():
    """Display an index of available sermons."""
    db = get_db()
    language = request.cookies.get("language", "en")
    
    # Debug log the query and language
    current_app.logger.info(f"Sermon index query with language: {language}")
    
    # Check for existing sermons and their insert_date values
    debug_cur = db.execute("SELECT sermon_title, insert_date FROM sermons WHERE language = ? ORDER BY insert_date DESC LIMIT 5", (language,))
    debug_sermons = debug_cur.fetchall()
    for sermon in debug_sermons:
        current_app.logger.info(f"DEBUG - Found sermon: {sermon['sermon_title']} with insert_date: {sermon['insert_date']}")
    
    # Execute the actual query
    cur = db.execute(
        "SELECT sermon_guid, sermon_title, audiofilename, transcription, categories "
        "FROM sermons WHERE language = ? ORDER BY insert_date DESC LIMIT 12", 
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
    response = make_response(render_template("sermons.html", sermons=processed_sermons))
    
    if current_app.config.get('TESTING', False):
        return response
        
    return set_visitor_id_cookie(response)


@bp.route("/api/sermons")
def get_sermons():
    """
    API endpoint to retrieve a list of sermons.
    
    Returns:
        JSON response with sermon data
    """
    try:
        page = int(request.args.get("page", 1))
    except ValueError:
        page = 1
    per_page = 20
    offset = (page - 1) * per_page
    db = get_db()
    language = request.cookies.get("language", "en")
    cur = db.execute(
        "SELECT sermon_guid, sermon_title, transcription, categories "
        "FROM sermons "
        "WHERE language = ? ORDER BY insert_date DESC "
        "LIMIT ? OFFSET ?",
        (language, per_page, offset)
    )
    sermons = cur.fetchall()

    processed_sermons = []
    for sermon in sermons:
        processed_sermons.append({
            "sermon_guid": sermon["sermon_guid"],
            "sermon_title": sermon["sermon_title"],
            "snippet": extract_first_sentences(sermon["transcription"]),
            "categories": sermon["categories"] or "Uncategorized"
        })
    return jsonify(processed_sermons)


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


@bp.route("/shared_images/<path:filename>")
def shared_images(filename):
    """
    Serve images from the shared images directory.
    
    Args:
        filename: Name of the image file
        
    Returns:
        Image file response
    """
    # If SHARED_IMAGES_DIR is configured, serve from there
    if current_app.config.get("SHARED_IMAGES_DIR"):
        return send_from_directory(current_app.config.get("SHARED_IMAGES_DIR"), filename)
    
    # Fall back to static/images if SHARED_IMAGES_DIR is not configured
    return send_from_directory(os.path.join(current_app.root_path, "static", "images"), filename)


@bp.route("/api/metrics", methods=["GET"])
def api_metrics():
    """
    API endpoint to retrieve search and access metrics.
    
    This endpoint requires API token authentication.
    
    Returns:
        JSON response with metrics data
    """
    is_valid, error_message = verify_api_token()
    if not is_valid:
        return jsonify({"error": error_message}), 403 if error_message == "Too many failed attempts. Try again later." else 401
    
    try:
        days = request.args.get("days", 30, type=int)
        limit = request.args.get("limit", 100, type=int)
        
        # Enforce reasonable limits
        days = max(1, min(days, 365))  # Between 1 and 365 days
        limit = max(10, min(limit, 1000))  # Between 10 and 1000 results
        
        metrics = get_search_metrics(days=days, limit=limit)
        return jsonify(metrics)
    except Exception as e:
        current_app.logger.error(f"Error retrieving metrics: {str(e)}", exc_info=True)
        return jsonify({"error": "An error occurred while retrieving metrics"}), 500


@bp.route("/api/update_stats", methods=["POST"])
def update_stats():
    """
    API endpoint to update sermon statistics.
    
    This creates statistics about the sermon database including
    word counts, most common words, and generates visualizations.
    
    Returns:
        Success or error message
    """
    is_valid, error_message = verify_api_token()
    if not is_valid:
        return jsonify({"error": error_message}), 403 if error_message == "Too many failed attempts. Try again later." else 401
    
    try:
        db = get_db()
        
        # Optimize by calculating total sermon count with a direct SQL query
        # Use fetchall() first and take the first row to be compatible with test mocks
        total_sermons_query = db.execute("SELECT COUNT(*) as count FROM sermons WHERE language = 'en'").fetchall()
        if not total_sermons_query:
            return jsonify({"error": "No sermons found"}), 404
            
        total_sermons = total_sermons_query[0]["count"] if "count" in total_sermons_query[0] else total_sermons_query[0][0]
        
        if total_sermons == 0:
            return jsonify({"error": "No sermons found"}), 404
            
        # Calculate total word count and find largest/shortest sermon with SQL
        # This avoids loading all transcriptions into memory at once
        word_counts_query = """
            SELECT sermon_title, sermon_guid,
                   LENGTH(transcription) - LENGTH(REPLACE(transcription, ' ', '')) + 1 as word_count
            FROM sermons 
            WHERE language = 'en'
        """
        word_counts = db.execute(word_counts_query).fetchall()
        
        total_word_count = 0
        largest_word_count = 0
        largest_sermon_title = ""
        largest_sermon_guid = ""
        smallest_word_count = float('inf')
        smallest_sermon_title = ""
        smallest_sermon_guid = ""
        
        for row in word_counts:
            word_count = row["word_count"]
            total_word_count += word_count
            
            if word_count > largest_word_count:
                largest_word_count = word_count
                largest_sermon_title = row["sermon_title"]
                largest_sermon_guid = row["sermon_guid"]
                
            if word_count < smallest_word_count:
                smallest_word_count = word_count
                smallest_sermon_title = row["sermon_title"]
                smallest_sermon_guid = row["sermon_guid"]
        
        average_words = total_word_count / total_sermons
        
        # Prepare sermon_stats structure for consistency with the rest of the code
        largest_sermon = {
            "sermon_title": largest_sermon_title,
            "word_count": largest_word_count,
            "sermon_guid": largest_sermon_guid
        }
        
        shortest_sermon = {
            "sermon_title": smallest_sermon_title,
            "word_count": smallest_word_count,
            "sermon_guid": smallest_sermon_guid
        }
        
        # Process top words in batches to reduce memory usage
        counter = Counter()
        batch_size = 100
        offset = 0
        
        while True:
            batch_query = f"""
                SELECT transcription FROM sermons 
                WHERE language = 'en'
                LIMIT {batch_size} OFFSET {offset}
            """
            batch = db.execute(batch_query).fetchall()
            
            if not batch:
                break
                
            for sermon in batch:
                text = sermon["transcription"].lower()
                text_clean = re.sub(r'[^\w\s]', '', text)
                words = text_clean.split()
                stop_words = set(stopwords.words('english'))
                filtered_words = [w for w in words if w not in stop_words]
                counter.update(filtered_words)
                
            offset += batch_size
            
        top_ten_list = [{"word": word, "count": count} for word, count in counter.most_common(10)]
        top_ten_words = json.dumps(top_ten_list)

        # Generate word cloud from the word count data we already have
        # Use shared images directory in production, fall back to static directory in development
        if current_app.config.get('SHARED_IMAGES_DIR'):
            images_dir = current_app.config.get('SHARED_IMAGES_DIR')
            if not os.path.exists(images_dir):
                os.makedirs(images_dir)
            word_cloud_path = os.path.join(images_dir, "data_cloud.png")
        else:
            # Development fallback
            static_images_dir = os.path.join(current_app.root_path, "static", "images")
            if not os.path.exists(static_images_dir):
                os.makedirs(static_images_dir)
            word_cloud_path = os.path.join(static_images_dir, "data_cloud.png")
        
        # Use the top words we already counted instead of regenerating from all text
        # This is much more efficient than feeding the entire corpus to WordCloud
        word_freq = {word: count for word, count in counter.most_common(300)}
        
        combined_stopwords = STOPWORDS.union(set(stopwords.words('english')))
        wc = WordCloud(
            width=800, 
            height=400, 
            background_color="white", 
            stopwords=combined_stopwords,
            max_words=150,
            prefer_horizontal=0.9
        ).generate_from_frequencies(word_freq)
        wc.to_file(word_cloud_path)

        # Generate bigram chart more efficiently
        # Process bigrams in batches simultaneously with the word counting
        bigram_counter = Counter()
        
        # Use the existing batch processing to also count bigrams
        bigram_batch_size = 100
        offset = 0
        
        while True:
            batch_query = f"""
                SELECT transcription FROM sermons 
                WHERE language = 'en'
                LIMIT {bigram_batch_size} OFFSET {offset}
            """
            batch = db.execute(batch_query).fetchall()
            
            if not batch:
                break
                
            for sermon in batch:
                text = sermon["transcription"].lower()
                text_clean = re.sub(r'[^\w\s]', '', text)
                words = text_clean.split()
                stop_words = set(stopwords.words('english'))
                filtered_words = [w for w in words if w not in stop_words]
                
                # Count bigrams in this batch
                if len(filtered_words) > 1:
                    for i in range(len(filtered_words) - 1):
                        bigram = f"{filtered_words[i]} {filtered_words[i+1]}"
                        bigram_counter[bigram] += 1
                
            offset += bigram_batch_size
        
        # Create bigram chart from the processed data
        top_ten_bigrams = bigram_counter.most_common(10)
        if top_ten_bigrams:
            bigrams_labels, bigrams_counts = zip(*top_ten_bigrams)
            plt.figure(figsize=(10, 6))
            plt.bar(bigrams_labels, bigrams_counts, color='skyblue')
            plt.xlabel('Bi-grams')
            plt.ylabel('Count')
            plt.title('Top 10 Bi-grams')
            plt.xticks(rotation=45, ha='right')
            plt.tight_layout()
            
            # Use shared images directory in production, fall back to static directory in development
            if current_app.config.get('SHARED_IMAGES_DIR'):
                images_dir = current_app.config.get('SHARED_IMAGES_DIR')
                bigram_chart_path = os.path.join(images_dir, "bigram_chart.png")
                plt.savefig(bigram_chart_path)
            else:
                # Development fallback
                static_images_dir = os.path.join(current_app.root_path, "static", "images")
                bigram_chart_path = os.path.join(static_images_dir, "bigram_chart.png")
                plt.savefig(bigram_chart_path)
            
            plt.close()

        # Find most common category using SQL for efficiency
        categories_query = """
            SELECT categories FROM sermons 
            WHERE language = 'en' AND categories IS NOT NULL AND categories != ''
        """
        categories_result = db.execute(categories_query).fetchall()
        
        category_counter = Counter()
        for row in categories_result:
            cats = row["categories"]
            if cats:
                for cat in cats.split(","):
                    cat = cat.strip()
                    if cat:
                        category_counter[cat] += 1
                        
        most_common_category = category_counter.most_common(1)[0][0] if category_counter else None
        now = datetime.datetime.now(datetime.UTC).isoformat()

        # Update database with new statistics
        db.execute("DELETE FROM stats_for_nerds")
        db.execute('''
             INSERT INTO stats_for_nerds 
             (id, total_sermons, average_words_per_sermon, 
              largest_sermon_title, largest_sermon_word_count, largest_sermon_guid,
              shortest_sermon_title, shortest_sermon_word_count, shortest_sermon_guid,
              top_ten_words, most_common_category, updated_at)
             VALUES (1, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        ''', (
             total_sermons,
             average_words,
             largest_sermon["sermon_title"],
             largest_sermon["word_count"],
             largest_sermon["sermon_guid"],
             shortest_sermon["sermon_title"],
             shortest_sermon["word_count"],
             shortest_sermon["sermon_guid"],
             top_ten_words,
             most_common_category,
             now
        ))
        db.commit()
        
        return "ok", 200
    except Exception as e:
        current_app.logger.error(f"Error updating stats: {str(e)}", exc_info=True)
        return jsonify({"error": "An error occurred while updating statistics"}), 500


@bp.route("/api/ai_sermon_content", methods=["POST"])
def upload_ai_sermon_content():
    """
    API endpoint to upload AI-generated sermon content.
    
    Validates and stores AI-generated content for sermons.
    
    Returns:
        Success or error message
    """
    is_valid, error_message = verify_api_token()
    if not is_valid:
        return jsonify({"error": error_message}), 401
    
    data = request.get_json()
    if not data:
        return jsonify({"error": "Invalid JSON payload"}), 400
    
    # Validate required fields
    required_fields = [
        "sermon_guid",
        "ai_summary",
        "ai_summary_es",
        "bible_books",
        "bible_books_es",
        "created_at",
        "key_quotes",
        "key_quotes_es",
        "sentiment",
        "sentiment_es",
        "sermon_style",
        "sermon_style_es",
        "status",
        "topics",
        "topics_es",
        "updated_at"
    ]
    for field in required_fields:
        if field not in data or data[field] is None:
            return jsonify({"error": f"Missing field: {field}"}), 400
    
    # Validate UUID format
    try:
        uuid.UUID(data["sermon_guid"])
    except ValueError:
        return jsonify({"error": "Invalid sermon_guid format. Must be a valid UUID."}), 400
    
    # Validate datetime fields
    for dt_field in ["created_at", "updated_at"]:
        try:
            datetime.datetime.strptime(data[dt_field], "%Y-%m-%d %H:%M:%S")
        except ValueError:
            return jsonify({"error": f"Invalid datetime format for {dt_field}. Expected YYYY-MM-DD HH:MM:SS"}), 400
    
    # Store AI content
    try:
        db = get_db()
        cursor = db.cursor()
        cursor.execute('''
            INSERT OR REPLACE INTO ai_sermon_content (
                sermon_guid, ai_summary, ai_summary_es, bible_books, bible_books_es, 
                created_at, key_quotes, key_quotes_es, sentiment, sentiment_es, 
                sermon_style, sermon_style_es, status, topics, topics_es, updated_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        ''', (
            data["sermon_guid"],
            data["ai_summary"],
            data["ai_summary_es"],
            data["bible_books"],
            data["bible_books_es"],
            data["created_at"],
            data["key_quotes"],
            data["key_quotes_es"],
            data["sentiment"],
            data["sentiment_es"],
            data["sermon_style"],
            data["sermon_style_es"],
            data["status"],
            data["topics"],
            data["topics_es"],
            data["updated_at"]
        ))
        db.commit()
    except Exception as e:
        current_app.logger.error(f"Database error: {e}", exc_info=True)
        return jsonify({"error": "Database error occurred."}), 500
    
    return jsonify({"message": "ok"}), 200


@bp.route("/upload_sermon", methods=["POST"])
@bp.route("/api/upload_sermon", methods=["POST"])
def upload_sermon():
    """
    API endpoint to upload a new sermon.
    
    Validates and stores a new sermon along with its audio file.
    
    Returns:
        Success or error message
    """
    is_valid, error_message = verify_api_token()
    if not is_valid:
        return jsonify({"error": error_message}), 403 if error_message == "Too many failed attempts. Try again later." else 401
    
    # Get form data
    audiofile = request.files.get("audiofile")
    transcription = request.form.get("Transcription")
    sermon_guid = request.form.get("SermonGUID")
    sermon_title = request.form.get("SermonTitle")
    language = request.form.get("Language")
    categories = request.form.get("Categories")
    church = request.form.get("Church")
    transcription_timings = request.form.get("TranscriptionTimings", None)
    
    # Validate required fields
    if not all([audiofile, transcription, sermon_guid, sermon_title, language, categories, church]):
        return jsonify({"error": "Missing required fields"}), 400
    
    try:
        # Save the audio file
        audio_filename = f"{sermon_guid}_{language}.mp3"
        audiofile_path = os.path.join(current_app.config.get("AUDIOFILES_DIR"), audio_filename)
        audiofile.save(audiofile_path)
        
        # Store sermon data in database
        db = get_db()
        db.execute('''
            INSERT INTO sermons (sermon_title, transcription, audiofilename, sermon_guid, language, categories, church, transcription_timings)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(sermon_guid, language) 
            DO UPDATE SET
                sermon_title = excluded.sermon_title,
                transcription = excluded.transcription,
                audiofilename = excluded.audiofilename,
                categories = excluded.categories,
                church = excluded.church,
                transcription_timings = excluded.transcription_timings
        ''', (sermon_title, transcription, audio_filename, sermon_guid, language, categories, church, transcription_timings))
        db.commit()
        
        return jsonify({"message": "Sermon uploaded successfully", "guid": sermon_guid}), 200
    except Exception as e:
        current_app.logger.error(f"Error uploading sermon: {str(e)}", exc_info=True)
        return jsonify({"error": "An error occurred while uploading the sermon."}), 500
