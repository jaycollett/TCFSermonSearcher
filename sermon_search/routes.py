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


@bp.route("/api/sermons")
def api_sermons():
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
        "WHERE language = ? ORDER BY sermon_title ASC "
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
        sermons = db.execute("SELECT sermon_title, transcription, categories FROM sermons where language = 'en'").fetchall()
        total_sermons = len(sermons)
        
        if total_sermons == 0:
            return jsonify({"error": "No sermons found"}), 404

        # Calculate sermon statistics
        total_words = 0
        sermon_stats = []
        for sermon in sermons:
            text = sermon["transcription"]
            word_count = len(text.split())
            total_words += word_count
            sermon_stats.append({
                "sermon_title": sermon["sermon_title"],
                "word_count": word_count,
                "categories": sermon["categories"] if sermon["categories"] else ""
            })

        average_words = total_words / total_sermons
        largest_sermon = max(sermon_stats, key=lambda x: x["word_count"])
        shortest_sermon = min(sermon_stats, key=lambda x: x["word_count"])

        # Analyze text content
        all_text = " ".join([sermon["transcription"] for sermon in sermons])
        all_text_clean = re.sub(r'[^\w\s]', '', all_text.lower())
        words = all_text_clean.split()
        stop_words = set(stopwords.words('english'))
        filtered_words = [w for w in words if w not in stop_words]
        counter = Counter(filtered_words)
        top_ten_list = [{"word": word, "count": count} for word, count in counter.most_common(10)]
        top_ten_words = json.dumps(top_ten_list)

        # Generate word cloud
        static_images_dir = os.path.join(current_app.root_path, "..", "static", "images")
        if not os.path.exists(static_images_dir):
            os.makedirs(static_images_dir)
        word_cloud_path = os.path.join(static_images_dir, "data_cloud.png")
        combined_stopwords = STOPWORDS.union(stop_words)
        wc = WordCloud(width=800, height=400, background_color="white", stopwords=combined_stopwords).generate(all_text)
        wc.to_file(word_cloud_path)

        # Generate bigram chart
        bigrams = zip(filtered_words, filtered_words[1:])
        bigram_list = [' '.join(bigram) for bigram in bigrams]
        bigram_counter = Counter(bigram_list)
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
            bigram_chart_path = os.path.join(static_images_dir, "bigram_chart.png")
            plt.savefig(bigram_chart_path)
            plt.close()

        # Find most common category
        category_counter = Counter()
        for sermon in sermons:
            cats = sermon["categories"]
            if cats:
                for cat in cats.split(","):
                    cat = cat.strip()
                    if cat:
                        category_counter[cat] += 1
        most_common_category = category_counter.most_common(1)[0][0] if category_counter else None
        now = datetime.datetime.utcnow().isoformat()

        # Update database with new statistics
        db.execute("DELETE FROM stats_for_nerds")
        db.execute('''
             INSERT INTO stats_for_nerds 
             (id, total_sermons, average_words_per_sermon, largest_sermon_title, largest_sermon_word_count,
              shortest_sermon_title, shortest_sermon_word_count, top_ten_words, most_common_category, updated_at)
             VALUES (1, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        ''', (
             total_sermons,
             average_words,
             largest_sermon["sermon_title"],
             largest_sermon["word_count"],
             shortest_sermon["sermon_title"],
             shortest_sermon["word_count"],
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