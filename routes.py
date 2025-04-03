import os
import re
import random
import sqlite3
import uuid
import json
import datetime
import math
import logging
import nltk
from collections import Counter

from flask import Blueprint, current_app, g, render_template, request, redirect, url_for, make_response, jsonify, send_from_directory
from flask_babel import gettext as _
from nltk.corpus import stopwords
nltk.download('stopwords', quiet=True)

# For headless chart generation
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from wordcloud import WordCloud, STOPWORDS

from models import get_db  # database connection function from models.py

# Create a blueprint for routes
bp = Blueprint("main", __name__)

# --- Utility Functions (used by the routes) ---

def get_client_ip():
    """Extract the real client IP behind a reverse proxy."""
    if request.headers.get('X-Forwarded-For'):
        return request.headers.get('X-Forwarded-For').split(',')[0]
    return request.remote_addr

def is_ip_banned(ip):
    """Check if the IP is banned and reset ban if expired."""
    db = get_db()
    cur = db.execute("SELECT failed_attempts, banned_until FROM ip_bans WHERE ip_address = ?", (ip,))
    row = cur.fetchone()
    if row:
        failed_attempts, banned_until = row["failed_attempts"], row["banned_until"]
        if banned_until:
            current_time = int(datetime.datetime.utcnow().timestamp())
            if banned_until > current_time:
                return True
            db.execute("UPDATE ip_bans SET failed_attempts = 0, banned_until = NULL WHERE ip_address = ?", (ip,))
            db.commit()
    return False

def get_all_categories(language):
    """Return a sorted list of distinct categories for the given language."""
    db = get_db()
    cur = db.execute("SELECT categories FROM sermons WHERE language = ?", (language,))
    rows = cur.fetchall()
    cats_set = set()
    for row in rows:
        if row["categories"]:
            for cat in row["categories"].split(","):
                trimmed = cat.strip()
                if trimmed:
                    cats_set.add(trimmed)
    return sorted(list(cats_set))

def extract_relevant_snippets(transcript, query, max_snippets=3, context_words=8):
    """Extract snippets of text surrounding the query."""
    matched_snippets = []
    escaped_query = re.escape(query)
    matches = list(re.finditer(escaped_query, transcript, re.IGNORECASE))
    if not matches:
        return ["(No exact match found)"]
    last_end = 0
    for match in matches:
        raw_start = max(0, match.start() - context_words * 5)
        raw_end = min(len(transcript), match.end() + context_words * 5)
        if raw_start > 0:
            adjusted_start = transcript.rfind(" ", 0, raw_start)
            start = adjusted_start + 1 if adjusted_start != -1 else raw_start
        else:
            start = raw_start
        if raw_end < len(transcript):
            adjusted_end = transcript.find(" ", raw_end)
            end = adjusted_end if adjusted_end != -1 else raw_end
        else:
            end = raw_end
        if start < last_end:
            continue
        snippet = transcript[start:end].strip()
        matched_snippets.append(snippet)
        last_end = end
        if len(matched_snippets) >= max_snippets:
            break
    return matched_snippets

def format_text_into_paragraphs(text, min_length=665):
    """Break long text into paragraphs for better readability."""
    if "\n\n" in text:
        paragraphs = [p.strip() for p in text.split("\n\n") if p.strip()]
        return ''.join(f"<p>{p}</p>" for p in paragraphs)
    else:
        sentences = re.split(r'(?<=[.!?])\s+', text)
        paragraphs = []
        current_para = ""
        for sentence in sentences:
            candidate = current_para + " " + sentence if current_para else sentence
            if len(candidate) < min_length:
                current_para = candidate
            else:
                paragraphs.append(candidate.strip())
                current_para = ""
        if current_para:
            paragraphs.append(current_para.strip())
        return ''.join(f"<p>{p}</p>" for p in paragraphs)

def highlight_search_terms(text, query):
    """Highlight search terms in the given text."""
    if not query or query.strip() == "":
        return text
    escaped_query = re.escape(query)
    regex = re.compile(rf'({escaped_query})', re.IGNORECASE)
    highlighted_text = regex.sub(r'<span class="highlight">\1</span>', text)
    return highlighted_text

def sanitize_search_term(term):
    """Sanitize and prepare search term for FTS query."""
    term = term.strip()
    term = re.sub(r'[^\w\s\-]', '', term)
    words = term.split()
    if len(words) == 1:
        return f'{term}*'
    return f'"{term}"'

# --- Route Handlers ---

@bp.route("/")
def index():
    greeting = _("Welcome to Sermon Search!")
    return render_template("index.html", greeting=greeting)

@bp.route("/set_language", methods=["POST"])
def set_language():
    selected_lang = request.form.get("language")
    if selected_lang not in ["en", "es"]:
        selected_lang = "en"
    resp = make_response(redirect(url_for("main.index")))
    resp.set_cookie("language", selected_lang, max_age=365*24*60*60)
    return resp

@bp.route('/sitemap.xml')
def sitemap():
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
    robots_txt = """User-agent: *
            Disallow: /
            Allow: /$
            Sitemap: https://sermonsearch.collett.us/sitemap.xml
            """
    return robots_txt, 200, {'Content-Type': 'text/plain'}

@bp.route("/search", methods=["GET"])
def search():
    query = request.args.get("q", "").strip()
    language = request.cookies.get("language", "en")
    selected_categories = request.args.getlist("categories")
    all_categories = get_all_categories(language)

    if not query:
        return render_template("search.html", all_categories=all_categories, selected_categories=selected_categories)

    try:
        page = int(request.args.get("page", 1))
        if page < 1:
            page = 1
    except ValueError:
        page = 1

    per_page = 10
    offset = (page - 1) * per_page
    sanitized_term = sanitize_search_term(query)
    results = []
    try:
        db = get_db()
        filter_clause = ""
        filter_params = []
        if selected_categories:
            conditions = []
            for cat in selected_categories:
                conditions.append("s.categories LIKE ?")
                filter_params.append(f"%{cat}%")
            filter_clause = " AND (" + " OR ".join(conditions) + ")"

        fts_query_str = f"sermon_title:{sanitized_term} OR transcription:{sanitized_term}"
        fts_sql = (
            "SELECT s.sermon_guid, s.sermon_title, s.audiofilename, s.transcription, s.categories "
            "FROM sermons s "
            "JOIN sermons_fts ON s.id = sermons_fts.rowid "
            "WHERE sermons_fts MATCH ? AND s.language = ? "
            f"{filter_clause} ORDER BY s.insert_date DESC LIMIT ? OFFSET ?"
        )
        params = [fts_query_str, language] + filter_params + [per_page, offset]
        cur = db.execute(fts_sql, params)
        sermons = cur.fetchall()

        count_sql = (
            "SELECT COUNT(*) as total "
            "FROM sermons s "
            "JOIN sermons_fts ON s.id = sermons_fts.rowid "
            "WHERE sermons_fts MATCH ? AND s.language = ? "
            f"{filter_clause}"
        )
        count_params = [fts_query_str, language] + filter_params
        cur = db.execute(count_sql, count_params)
        total_count = cur.fetchone()["total"]

        if not sermons:
            like_query = f"%{query}%"
            fallback_sql = (
                "SELECT s.sermon_guid, s.sermon_title, s.audiofilename, s.transcription, s.categories "
                "FROM sermons s "
                "WHERE s.transcription LIKE ? AND s.language = ? "
                f"{filter_clause} ORDER BY s.insert_date DESC LIMIT ? OFFSET ?"
            )
            params = [like_query, language] + filter_params + [per_page, offset]
            cur = db.execute(fallback_sql, params)
            sermons = cur.fetchall()
            count_sql = (
                "SELECT COUNT(*) as total "
                "FROM sermons s "
                "WHERE s.transcription LIKE ? AND s.language = ? "
                f"{filter_clause}"
            )
            count_params = [like_query, language] + filter_params
            cur = db.execute(count_sql, count_params)
            total_count = cur.fetchone()["total"]

        total_pages = math.ceil(total_count / per_page) if total_count > 0 else 1

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

        current_app.logger.debug(f"Total results found: {len(results)} out of {total_count}")

    except Exception as e:
        current_app.logger.error(f"Error during search: {str(e)}", exc_info=True)
        return render_template("error.html", message=_("An error occurred while processing your search. Please try again."))

    return render_template("results.html", 
                           query=query, 
                           results=results,
                           highlight_search_terms=highlight_search_terms,
                           all_categories=all_categories,
                           selected_categories=selected_categories,
                           page=page,
                           total_pages=total_pages,
                           total_count=total_count)

@bp.route("/sermon/<sermon_guid>")
def sermon_detail(sermon_guid):
    db = get_db()
    language = request.cookies.get("language", "en")
    query = request.args.get("q", "").strip()
    selected_categories = request.args.getlist("categories")
    page = request.args.get("page", 1)
    cur = db.execute(
        "SELECT * FROM sermons WHERE sermon_guid = ? AND language = ?",
        (sermon_guid, language),
    )
    sermon = cur.fetchone()
    if not sermon:
        cur = db.execute(
            "SELECT * FROM sermons WHERE sermon_guid = ? AND language = 'en'",
            (sermon_guid,),
        )
        sermon = cur.fetchone()
    if not sermon:
        return _("Sermon not found"), 404

    cur = db.execute(
        "SELECT * FROM ai_sermon_content WHERE sermon_guid = ?",
        (sermon_guid,)
    )
    ai_content = cur.fetchone()

    formatted_transcript = format_text_into_paragraphs(sermon["transcription"])
    highlighted_transcript = highlight_search_terms(formatted_transcript, query)

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
    db = get_db()
    row = db.execute("SELECT * FROM stats_for_nerds WHERE id = 1").fetchone()
    if row:
        context = {
            "total_sermons": row["total_sermons"],
            "average_words_per_sermon": row["average_words_per_sermon"],
            "largest_sermon_title": row["largest_sermon_title"],
            "largest_sermon_word_count": row["largest_sermon_word_count"],
            "shortest_sermon_title": row["shortest_sermon_title"],
            "shortest_sermon_word_count": row["shortest_sermon_word_count"],
            "top_ten_words": json.loads(row["top_ten_words"]) if row["top_ten_words"] else [],
            "most_common_category": row["most_common_category"],
            "updated_at": row["updated_at"],
        }
    else:
        context = {
            "total_sermons": 0,
            "average_words_per_sermon": 0,
            "largest_sermon_title": "No data",
            "largest_sermon_word_count": 0,
            "shortest_sermon_title": "No data",
            "shortest_sermon_word_count": 0,
            "top_ten_words": [],
            "most_common_category": "N/A",
            "updated_at": "N/A",
        }
    return render_template("stats.html", **context)

@bp.route("/sermons")
def sermon_index():
    db = get_db()
    language = request.cookies.get("language", "en")
    cur = db.execute("SELECT sermon_guid, sermon_title, SUBSTR(transcription, 1, 250) as transcription, categories FROM sermons WHERE language = ? ORDER BY sermon_title ASC LIMIT 12", (language,))
    sermons = cur.fetchall()

    def extract_first_sentences(text, min_sentences=3, max_sentences=4):
        if not text:
            return "(No transcription available)"
        sentences = re.split(r'(?<=[.!?])\s+', text)
        snippet = " ".join(sentences[:random.randint(min_sentences, max_sentences)])
        return snippet

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

    def extract_first_sentences(text, min_sentences=3, max_sentences=4):
        if not text:
            return "(No transcription available)"
        sentences = re.split(r'(?<=[.!?])\s+', text)
        snippet = " ".join(sentences[:random.randint(min_sentences, max_sentences)])
        return snippet

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
    return send_from_directory(current_app.config.get("AUDIOFILES_DIR"), filename)

@bp.route("/api/update_stats", methods=["POST"])
def update_stats():
    ip = get_client_ip()
    db = get_db()
    if is_ip_banned(ip):
        return jsonify({"error": "Too many failed attempts. Try again later."}), 403
    api_token = request.headers.get("X-API-Token")
    if not api_token or api_token != os.environ.get("SERMON_API_TOKEN", ""):
        cur = db.execute("SELECT failed_attempts FROM ip_bans WHERE ip_address = ?", (ip,))
        row = cur.fetchone()
        attempts = row["failed_attempts"] + 1 if row else 1
        if attempts >= 3:
            banned_until = int(datetime.datetime.utcnow().timestamp()) + 86400
            db.execute("REPLACE INTO ip_bans (ip_address, failed_attempts, banned_until) VALUES (?, ?, ?)", (ip, attempts, banned_until))
        else:
            db.execute("REPLACE INTO ip_bans (ip_address, failed_attempts, banned_until) VALUES (?, ?, NULL)", (ip, attempts))
        db.commit()
        return jsonify({"error": "Unauthorized"}), 401

    sermons = db.execute("SELECT sermon_title, transcription, categories FROM sermons where language = 'en'").fetchall()
    total_sermons = len(sermons)
    if total_sermons == 0:
        return jsonify({"error": "No sermons found"}), 404

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

    all_text = " ".join([sermon["transcription"] for sermon in sermons])
    all_text_clean = re.sub(r'[^\w\s]', '', all_text.lower())
    words = all_text_clean.split()
    stop_words = set(stopwords.words('english'))
    filtered_words = [w for w in words if w not in stop_words]
    counter = Counter(filtered_words)
    top_ten_list = [{"word": word, "count": count} for word, count in counter.most_common(10)]
    top_ten_words = json.dumps(top_ten_list)

    static_images_dir = os.path.join(current_app.root_path, "static", "images")
    if not os.path.exists(static_images_dir):
        os.makedirs(static_images_dir)
    word_cloud_path = os.path.join(static_images_dir, "data_cloud.png")
    combined_stopwords = STOPWORDS.union(stop_words)
    wc = WordCloud(width=800, height=400, background_color="white", stopwords=combined_stopwords).generate(all_text)
    wc.to_file(word_cloud_path)

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

@bp.route("/api/ai_sermon_content", methods=["POST"])
def upload_ai_sermon_content():
    api_token = request.headers.get("X-API-Token")
    if not api_token or api_token != os.environ.get("SERMON_API_TOKEN", ""):
        return jsonify({"error": "Unauthorized"}), 401
    data = request.get_json()
    if not data:
        return jsonify({"error": "Invalid JSON payload"}), 400
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
    try:
        uuid.UUID(data["sermon_guid"])
    except ValueError:
        return jsonify({"error": "Invalid sermon_guid format. Must be a valid UUID."}), 400
    for dt_field in ["created_at", "updated_at"]:
        try:
            datetime.datetime.strptime(data[dt_field], "%Y-%m-%d %H:%M:%S")
        except ValueError:
            return jsonify({"error": f"Invalid datetime format for {dt_field}. Expected YYYY-MM-DD HH:MM:SS"}), 400
    db = get_db()
    try:
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
    except sqlite3.Error as e:
        current_app.logger.error(f"Database error: {e}")
        return jsonify({"error": "Database error occurred."}), 500
    return jsonify({"message": "ok"}), 200

@bp.route("/upload_sermon", methods=["POST"])
@bp.route("/api/upload_sermon", methods=["POST"])
def upload_sermon():
    ip = get_client_ip()
    if is_ip_banned(ip):
        return jsonify({"error": "Too many failed attempts. Try again later."}), 403
    api_token = request.headers.get("X-API-Token")
    db = get_db()
    if not api_token or api_token != os.environ.get("SERMON_API_TOKEN", ""):
        cur = db.execute("SELECT failed_attempts FROM ip_bans WHERE ip_address = ?", (ip,))
        row = cur.fetchone()
        attempts = row["failed_attempts"] + 1 if row else 1
        if attempts >= 3:
            banned_until = int(datetime.datetime.utcnow().timestamp()) + 86400
            db.execute("REPLACE INTO ip_bans (ip_address, failed_attempts, banned_until) VALUES (?, ?, ?)", (ip, attempts, banned_until))
        else:
            db.execute("REPLACE INTO ip_bans (ip_address, failed_attempts, banned_until) VALUES (?, ?, NULL)", (ip, attempts))
        db.commit()
        return jsonify({"error": "Unauthorized"}), 401
    db.execute("DELETE FROM ip_bans WHERE ip_address = ?", (ip,))
    db.commit()
    audiofile = request.files.get("audiofile")
    transcription = request.form.get("Transcription")
    sermon_guid = request.form.get("SermonGUID")
    sermon_title = request.form.get("SermonTitle")
    language = request.form.get("Language")
    categories = request.form.get("Categories")
    church = request.form.get("Church")
    transcription_timings = request.form.get("TranscriptionTimings", None)
    if not all([audiofile, transcription, sermon_guid, sermon_title, language, categories, church]):
        return jsonify({"error": "Missing required fields"}), 400
    audio_filename = f"{sermon_guid}_{language}.mp3"
    audiofile.save(os.path.join("/data/audiofiles", audio_filename))
    try:
        with sqlite3.connect(current_app.config.get("DATABASE")) as conn:
            cursor = conn.cursor()
            cursor.execute('''
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
            conn.commit()
    except sqlite3.IntegrityError:
        return jsonify({"error": "Database error occurred."}), 400
    return jsonify({"message": "Sermon uploaded successfully", "guid": sermon_guid}), 200
