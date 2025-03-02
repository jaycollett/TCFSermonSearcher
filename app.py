import os
import re
import logging
import random
import sqlite3
import uuid
import datetime
from flask import Flask, g, render_template, request, send_from_directory, redirect, url_for, make_response, jsonify
from flask_babel import Babel, gettext as _

app = Flask(__name__)
DATABASE = "/data/sermons.db"
AUDIOFILES_DIR = "/data/audiofiles"

# Ensure data directories exist
os.makedirs(os.path.dirname(DATABASE), exist_ok=True)
os.makedirs(AUDIOFILES_DIR, exist_ok=True)

# Configure logging
logging.basicConfig(level=logging.DEBUG)

# Babel configuration
app.config['BABEL_DEFAULT_LOCALE'] = 'en'
app.config['BABEL_SUPPORTED_LOCALES'] = ['en', 'es']

def get_locale():
    return request.cookies.get('language', 'en')

babel = Babel(app, locale_selector=get_locale)

def get_db():
    db = getattr(g, '_database', None)
    if db is None:
        db = g._database = sqlite3.connect(DATABASE)
        db.row_factory = sqlite3.Row
    return db

def init_db():
    """Ensure the database exists and initialize tables."""

    app.logger.info("Initializing database...")

    # Check if the database file exists, if not, create it
    if not os.path.exists(DATABASE):
        app.logger.info(f"Database file '{DATABASE}' does not exist. Creating it.")
        open(DATABASE, 'w').close()

    with sqlite3.connect(DATABASE) as conn:
        cursor = conn.cursor()

        try:
            app.logger.info("Creating sermons table...")
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS sermons (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    sermon_title TEXT NOT NULL,
                    transcription TEXT NOT NULL,
                    audiofilename TEXT,
                    sermon_guid VARCHAR(40) UNIQUE,
                    language VARCHAR(2) DEFAULT 'en',
                    categories TEXT,
                    insert_date DATETIME DEFAULT CURRENT_TIMESTAMP,
                    church NVARCHAR(10)
                )
            ''')
            conn.commit()
            app.logger.info("Sermons table created successfully.")
        except sqlite3.Error as e:
            app.logger.error(f"Error creating sermons table: {e}")

        try:
            app.logger.info("Creating ip_bans table...")
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS ip_bans (
                    ip_address TEXT PRIMARY KEY,
                    failed_attempts INTEGER DEFAULT 0,
                    banned_until INTEGER 
                )
            ''')
            conn.commit()
            app.logger.info("ip_bans table created successfully.")
        except sqlite3.Error as e:
            app.logger.error(f"Error creating ip_bans table: {e}")

        try:
            app.logger.info("Creating sermons_fts table...")
            cursor.execute('''
                CREATE VIRTUAL TABLE IF NOT EXISTS sermons_fts USING fts5(
                    sermon_guid, sermon_title, transcription, 
                    audiofilename UNINDEXED, language UNINDEXED, 
                    categories UNINDEXED, church UNINDEXED,
                    content='sermons', content_rowid='id',
                    tokenize='unicode61',  
                    prefix='2,3'
                )
            ''')
            conn.commit()

            app.logger.info("sermons_fts table created successfully.")
        except sqlite3.Error as e:
            app.logger.error(f"Error creating sermons_fts table: {e}")

        try:
            app.logger.info("Creating triggers...")
            cursor.execute('''
                CREATE TRIGGER IF NOT EXISTS sermons_ai AFTER INSERT ON sermons
                BEGIN
                    INSERT INTO sermons_fts(rowid, sermon_guid, sermon_title, transcription, audiofilename, language, categories, church)
                    VALUES (new.id, new.sermon_guid, new.sermon_title, new.transcription, new.audiofilename, new.language, new.categories, new.church);
                END;
            ''')
            cursor.execute('''
                CREATE TRIGGER IF NOT EXISTS sermons_ad AFTER DELETE ON sermons
                BEGIN
                    DELETE FROM sermons_fts WHERE rowid = old.id;
                END;
            ''')
            cursor.execute('''
                CREATE TRIGGER IF NOT EXISTS sermons_au AFTER UPDATE ON sermons
                BEGIN
                    DELETE FROM sermons_fts WHERE rowid = old.id;
                    INSERT INTO sermons_fts(rowid, sermon_guid, sermon_title, transcription, audiofilename, language, categories, church)
                    VALUES (new.id, new.sermon_guid, new.sermon_title, new.transcription, new.audiofilename, new.language, new.categories, new.church);
                END;
            ''')
            conn.commit()
            app.logger.info("Triggers created successfully.")
        except sqlite3.Error as e:
            app.logger.error(f"Error creating triggers: {e}")

    app.logger.info("Database initialization complete.")

init_db()

@app.teardown_appcontext
def close_connection(exception):
    db = getattr(g, '_database', None)
    if db is not None:
        db.close()

def is_ip_banned(ip):
    """Check if the IP is currently banned and handle expired bans using Unix epoch timestamps."""
    db = get_db()
    cur = db.execute("SELECT failed_attempts, banned_until FROM ip_bans WHERE ip_address = ?", (ip,))
    row = cur.fetchone()

    if row:
        failed_attempts, banned_until = row["failed_attempts"], row["banned_until"]
        
        if banned_until:  # `banned_until` is stored as an integer (epoch time in seconds)
            current_time = int(datetime.datetime.utcnow().timestamp())  # Current time in epoch seconds
            
            if banned_until > current_time:
                return True  # Still banned
            
            # Ban has expired, reset failed attempts and remove ban
            db.execute("UPDATE ip_bans SET failed_attempts = 0, banned_until = NULL WHERE ip_address = ?", (ip,))
            db.commit()

    return False

def get_client_ip():
    """Extract the real client IP behind a reverse proxy."""
    if request.headers.get('X-Forwarded-For'):
        return request.headers.get('X-Forwarded-For').split(',')[0]  # First IP in the list is the real client IP
    return request.remote_addr  # Fallback if header is missing

def extract_relevant_snippets(transcript, query, max_snippets=3, context_words=8):
    """Extract up to `max_snippets` of text surrounding the search query."""
    matched_snippets = []
    escaped_query = re.escape(query)
    
    # Find all occurrences of the query in the text
    matches = list(re.finditer(escaped_query, transcript, re.IGNORECASE))

    if not matches:
        return ["(No exact match found)"]

    last_end = 0  # Track the last snippet end position to avoid excessive overlap
    for match in matches:
        start = max(0, match.start() - context_words * 5)
        end = min(len(transcript), match.end() + context_words * 5)

        # Avoid extracting overlapping snippets
        if start < last_end:
            continue

        snippet = transcript[start:end].strip()
        matched_snippets.append(snippet)
        last_end = end  # Update last snippet position

        if len(matched_snippets) >= max_snippets:
            break

    return matched_snippets

def format_text_into_paragraphs(text, min_sentences=3, max_sentences=6):
    """Breaks long text into readable paragraphs by grouping sentences."""
    sentences = re.split(r'(?<=[.!?])\s+', text)
    paragraphs = []
    i = 0
    while i < len(sentences):
        num_sentences = random.randint(min_sentences, max_sentences)
        paragraph = ' '.join(sentences[i:i + num_sentences])
        paragraphs.append(paragraph.strip())
        i += num_sentences
    return ''.join(f"<p>{p}</p>" for p in paragraphs)

def highlight_search_terms(text, query):
    """Wraps search terms in a highlight span tag while preserving original case and ensuring case-insensitive matching."""
    if not query or query.strip() == "":
        return text

    escaped_query = re.escape(query)
    
    def replace_match(match):
        return f'<span class="highlight">{match.group()}</span>'

    # Perform case-insensitive substitution while keeping the original case
    regex = re.compile(rf'\b{escaped_query}\b', re.IGNORECASE)

    highlighted_text = regex.sub(replace_match, text)
    return highlighted_text





def inject_language():
    language = request.cookies.get('language', 'en')
    return dict(language=language)

@app.route("/")
def index():
    greeting = _( "Welcome to Sermon Search!")
    return render_template("index.html", greeting=greeting)

@app.route("/set_language", methods=["POST"])
def set_language():
    """Update the language cookie and redirect to the home page."""
    selected_lang = request.form.get("language")
    if selected_lang not in ["en", "es"]:
        selected_lang = "en"
    resp = make_response(redirect(url_for("index")))
    resp.set_cookie("language", selected_lang, max_age=365*24*60*60)
    return resp

@app.route('/sitemap.xml')
def sitemap():
    return """<?xml version="1.0" encoding="UTF-8"?>
                <urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">
                <url>
                    <loc>https://sermonsearch.collett.us/</loc>
                    <priority>1.0</priority>
                </url>
                </urlset>
                """, 200, {'Content-Type': 'application/xml'}


@app.route('/robots.txt')
def robots():
    return """User-agent: *
            Disallow: /
            Allow: /$
            Sitemap: https://sermonsearch.collett.us/sitemap.xml
            """, 200, {'Content-Type': 'text/plain'}


@app.route("/search", methods=["GET"])
def search():
    """Handles searching for sermons using Full-Text Search (FTS5) and filters results by language."""
    query = request.args.get("q", "").strip()
    if not query:
        return render_template("search.html")

    app.logger.info(f"Search query received: {query}")

    words = query.split()
    fts_query = query + '*' if len(words) == 1 and 2 <= len(query) <= 5 else query  # Enables prefix search

    results = []
    try:
        language = request.cookies.get("language", "en")
        db = get_db()

        # First, try FTS5 prefix searching
        cur = db.execute(
            "SELECT sermon_guid, sermon_title, audiofilename, transcription FROM sermons_fts WHERE sermons_fts MATCH ? AND language = ? LIMIT 25",
            (fts_query, language)
        )
        sermons = cur.fetchall()

        # If FTS5 finds nothing, fallback to LIKE for substring match
        if not sermons:
            like_query = f"%{query}%"
            cur = db.execute(
                "SELECT sermon_guid, sermon_title, audiofilename, transcription FROM sermons WHERE transcription LIKE ? AND language = ? LIMIT 25",
                (like_query, language)
            )
            sermons = cur.fetchall()

        for sermon in sermons:
            snippets = extract_relevant_snippets(sermon["transcription"], query)
            if not snippets or snippets == ["(No exact match found)"]:
                snippets = [sermon["transcription"][:200]]  # Fallback to first 200 chars
            
            results.append({
                "sermon_guid": sermon["sermon_guid"],
                "sermon_title": sermon["sermon_title"],
                "audiofilename": sermon["audiofilename"],
                "snippets": snippets
        })

        app.logger.debug(f"Total results found: {len(results)}")

    except Exception as e:
        app.logger.error(f"Error during search: {str(e)}", exc_info=True)
        return render_template("error.html", message=_("An error occurred while processing your search. Please try again."))

    return render_template("results.html", 
                            query=query, 
                            results=results,
                            highlight_search_terms=highlight_search_terms)  # Pass the function


@app.route("/sermon/<sermon_guid>")
def sermon_detail(sermon_guid):
    """Retrieve and display a sermon with formatted transcription and highlights."""
    db = get_db()
    cur = db.execute("SELECT * FROM sermons WHERE sermon_guid = ?", (sermon_guid,))
    sermon = cur.fetchone()

    if not sermon:
        return _("Sermon not found"), 404

    query = request.args.get("q", "").strip()

    # Format and highlight transcription
    formatted_transcript = format_text_into_paragraphs(sermon["transcription"])
    highlighted_transcript = highlight_search_terms(formatted_transcript, query)

    return render_template("sermon.html", sermon=sermon, formatted_transcript=highlighted_transcript, query=query)


@app.route("/sermons")
def sermon_index():
    db = get_db()
    language = request.cookies.get("language", "en")
    cur = db.execute("SELECT sermon_guid, sermon_title, audiofilename FROM sermons WHERE language = ? ORDER BY sermon_title ASC", (language,))
    sermons = cur.fetchall()
    return render_template("sermons.html", sermons=sermons)

@app.route("/audiofiles/<path:filename>")
def audiofiles(filename):
    """Serve audio files from /data/audiofiles directory."""
    return send_from_directory(AUDIOFILES_DIR, filename)

@app.route("/upload_sermon", methods=["POST"])
def upload_sermon():
    """API Endpoint to upload sermon audio, transcription, and metadata with IP ban logic."""
    ip = get_client_ip()  # Get actual client IP

    # Check if IP is banned
    if is_ip_banned(ip):
        return jsonify({"error": "Too many failed attempts. Try again later."}), 403

    api_token = request.headers.get("X-API-Token")
    db = get_db()

    if not api_token or api_token != os.environ.get("SERMON_API_TOKEN", ""):
        cur = db.execute("SELECT failed_attempts FROM ip_bans WHERE ip_address = ?", (ip,))
        row = cur.fetchone()
        attempts = row["failed_attempts"] + 1 if row else 1

        if attempts >= 3:
            banned_until = int(datetime.datetime.utcnow().timestamp()) + 86400  # 24 hours from now
            db.execute("REPLACE INTO ip_bans (ip_address, failed_attempts, banned_until) VALUES (?, ?, ?)", (ip, attempts, banned_until))
        else:
            db.execute("REPLACE INTO ip_bans (ip_address, failed_attempts, banned_until) VALUES (?, ?, NULL)", (ip, attempts))

        db.commit()
        return jsonify({"error": "Unauthorized"}), 401

    # Reset failed attempts on successful authentication
    db.execute("DELETE FROM ip_bans WHERE ip_address = ?", (ip,))
    db.commit()

    # Process sermon upload
    audiofile = request.files.get("audiofile")
    transcription = request.form.get("Transcription")
    sermon_guid = request.form.get("SermonGUID")
    sermon_title = request.form.get("SermonTitle")
    language = request.form.get("Language")
    categories = request.form.get("Categories")
    church = request.form.get("Church")

    if not all([audiofile, transcription, sermon_guid, sermon_title, language, categories, church]):
        return jsonify({"error": "Missing required fields"}), 400

    audio_filename = f"{sermon_guid}.mp3"
    audiofile.save(os.path.join("/data/audiofiles", audio_filename))

    try:
        with sqlite3.connect(DATABASE) as conn:
            cursor = conn.cursor()
            cursor.execute('''
                INSERT INTO sermons (sermon_title, transcription, audiofilename, sermon_guid, language, categories, church)
                VALUES (?, ?, ?, ?, ?, ?, ?)
            ''', (sermon_title, transcription, audio_filename, sermon_guid, language, categories, church))
            conn.commit()
    except sqlite3.IntegrityError:
        return jsonify({"error": "Sermon GUID must be unique."}), 400

    return jsonify({"message": "Sermon uploaded successfully", "guid": sermon_guid}), 200


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000, debug=True)
