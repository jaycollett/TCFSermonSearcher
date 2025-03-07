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
app.config['BABEL_TRANSLATION_DIRECTORIES'] = 'translations'

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

    if not os.path.exists(DATABASE):
        app.logger.info(f"Database file '{DATABASE}' does not exist. Creating it.")
        open(DATABASE, 'w').close()

    with sqlite3.connect(DATABASE) as conn:
        cursor = conn.cursor()

        # Enable WAL mode if not already enabled
        cursor.execute('PRAGMA journal_mode;')
        journal_mode = cursor.fetchone()[0]
        if journal_mode.lower() != 'wal':
            cursor.execute('PRAGMA journal_mode=WAL;')

        try:
            app.logger.info("Creating sermons table...")
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS sermons (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    sermon_title TEXT NOT NULL,
                    transcription TEXT NOT NULL,
                    audiofilename TEXT,
                    sermon_guid VARCHAR(40) NOT NULL,
                    language VARCHAR(2) NOT NULL DEFAULT 'en',
                    categories TEXT,
                    ai_summary TEXT,
                    ai_identified_books TEXT,
                    insert_date DATETIME DEFAULT CURRENT_TIMESTAMP,
                    church NVARCHAR(10),
                    UNIQUE (sermon_guid, language)
                )
            ''')
            cursor.execute('CREATE INDEX IF NOT EXISTS idx_sermon_guid ON sermons (sermon_guid)')
            cursor.execute('CREATE INDEX IF NOT EXISTS idx_sermons_language ON sermons(language);')
            cursor.execute('CREATE INDEX IF NOT EXISTS idx_sermons_categories ON sermons(categories);')
            cursor.execute('CREATE INDEX IF NOT EXISTS idx_sermons_ai_identified_books ON sermons(ai_identified_books);')
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
                    categories, church UNINDEXED,
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
            cursor.executescript('''
                CREATE TRIGGER IF NOT EXISTS sermons_ai AFTER INSERT ON sermons BEGIN
                    INSERT INTO sermons_fts(rowid, sermon_guid, sermon_title, transcription, audiofilename, categories, language, church)
                    VALUES (new.id, new.sermon_guid, new.sermon_title, new.transcription, new.audiofilename, new.categories, new.language, new.church);
                END;

                CREATE TRIGGER IF NOT EXISTS sermons_ad AFTER DELETE ON sermons BEGIN
                    DELETE FROM sermons_fts WHERE rowid = old.id;
                END;

                CREATE TRIGGER IF NOT EXISTS sermons_au AFTER UPDATE ON sermons BEGIN
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

def get_all_categories(language):
    """Return a sorted list of distinct category values for the given language."""
    db = get_db()
    cur = db.execute("SELECT categories FROM sermons WHERE language = ?", (language,))
    rows = cur.fetchall()
    cats_set = set()
    for row in rows:
        if row["categories"]:
            # Split on comma, strip whitespace, and add non-empty values.
            for cat in row["categories"].split(","):
                trimmed = cat.strip()
                if trimmed:
                    cats_set.add(trimmed)
    return sorted(list(cats_set))


def extract_relevant_snippets(transcript, query, max_snippets=3, context_words=8):
    """Extract up to `max_snippets` of text surrounding the search query without cutting words in half."""
    matched_snippets = []
    escaped_query = re.escape(query)
    
    # Find all occurrences of the query in the transcript (case-insensitive)
    matches = list(re.finditer(escaped_query, transcript, re.IGNORECASE))
    if not matches:
        return ["(No exact match found)"]
    
    last_end = 0  # Track the last snippet's end to avoid overlaps
    
    for match in matches:
        # Calculate raw boundaries using context_words multiplier
        raw_start = max(0, match.start() - context_words * 5)
        raw_end = min(len(transcript), match.end() + context_words * 5)
        
        # Adjust start: if not at beginning, move back to the previous space to avoid cutting a word.
        if raw_start > 0:
            adjusted_start = transcript.rfind(" ", 0, raw_start)
            start = adjusted_start + 1 if adjusted_start != -1 else raw_start
        else:
            start = raw_start
        
        # Adjust end: if not at end, move forward to the next space.
        if raw_end < len(transcript):
            adjusted_end = transcript.find(" ", raw_end)
            end = adjusted_end if adjusted_end != -1 else raw_end
        else:
            end = raw_end
        
        # Avoid overlapping snippets
        if start < last_end:
            continue

        snippet = transcript[start:end].strip()
        matched_snippets.append(snippet)
        last_end = end
        
        if len(matched_snippets) >= max_snippets:
            break

    return matched_snippets


def format_text_into_paragraphs(text, min_length=665):
    """
    Breaks long text into readable paragraphs.
    If double newlines exist, uses them as paragraph breaks.
    Otherwise, splits the text by sentence endings and combines sentences until each paragraph
    reaches at least min_length characters (if possible).
    """
    # Use existing paragraph breaks if available
    if "\n\n" in text:
        paragraphs = [p.strip() for p in text.split("\n\n") if p.strip()]
        return ''.join(f"<p>{p}</p>" for p in paragraphs)
    else:
        # Split by sentence-ending punctuation
        sentences = re.split(r'(?<=[.!?])\s+', text)
        paragraphs = []
        current_para = ""
        for sentence in sentences:
            # If current paragraph is empty, start with the sentence; otherwise, append it.
            if current_para:
                candidate = current_para + " " + sentence
            else:
                candidate = sentence
            # If candidate paragraph is still too short, continue adding sentences
            if len(candidate) < min_length:
                current_para = candidate
            else:
                paragraphs.append(candidate.strip())
                current_para = ""
        # Append any remaining text as a paragraph
        if current_para:
            paragraphs.append(current_para.strip())
        return ''.join(f"<p>{p}</p>" for p in paragraphs)


def highlight_search_terms(text, query):
    """Wraps search terms in a highlight span tag while preserving original case and ensuring case-insensitive matching."""
    if not query or query.strip() == "":
        return text

    escaped_query = re.escape(query)
    # Use a capturing group without relying on word boundaries for more flexibility.
    regex = re.compile(rf'({escaped_query})', re.IGNORECASE)

    highlighted_text = regex.sub(r'<span class="highlight">\1</span>', text)
    return highlighted_text

@app.template_filter('truncate_text')
def truncate_text_filter(s, max_length=165):
    if not s:
        return ''
    if len(s) <= max_length:
        return s
    cutoff = s[:max_length]
    last_space = cutoff.rfind(' ')
    if last_space != -1:
        return cutoff[:last_space] + '...'
    else:
        return cutoff + '...'


@app.context_processor
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

def sanitize_search_term(term):
    term = term.strip()
    term = re.sub(r'[^\w\s\-]', '', term)
    # Always use prefix matching for single tokens
    words = term.split()
    if len(words) == 1:
        return f'{term}*'
    return f'"{term}"'


@app.route("/search", methods=["GET"])
def search():
    query = request.args.get("q", "").strip()
    language = request.cookies.get("language", "en")
    # Get filter selections (may be an empty list)
    selected_categories = request.args.getlist("categories")
    # Get the full list of distinct categories for the current language
    all_categories = get_all_categories(language)

    # If no query is entered, simply render the search page with filters
    if not query:
        return render_template("search.html", all_categories=all_categories, selected_categories=selected_categories)

    # Sanitize the search term for FTS
    sanitized_term = sanitize_search_term(query)
    results = []
    try:
        db = get_db()

        # Build extra SQL conditions if filters were selected.
        filter_clause = ""
        filter_params = []
        if selected_categories:
            conditions = []
            # Use the base table alias (s) for filtering on unindexed columns in the join query.
            for cat in selected_categories:
                conditions.append("s.categories LIKE ?")
                filter_params.append(f"%{cat}%")
            filter_clause = " AND (" + " OR ".join(conditions) + ")"

        # Build the FTS query string to search in specific columns.
        fts_query_str = f"sermon_title:{sanitized_term} OR transcription:{sanitized_term}"

        # Query using a join between the base table and the FTS virtual table.
        fts_sql = (
            "SELECT s.sermon_guid, s.sermon_title, s.audiofilename, s.transcription, s.categories "
            "FROM sermons s "
            "JOIN sermons_fts ON s.id = sermons_fts.rowid "
            "WHERE sermons_fts MATCH ? AND s.language = ? "
            f"{filter_clause} LIMIT 25"
        )
        params = [fts_query_str, language] + filter_params
        cur = db.execute(fts_sql, params)
        sermons = cur.fetchall()

        # Fallback: if no FTS results, do a LIKE search on the base table.
        if not sermons:
            like_query = f"%{query}%"
            fallback_sql = (
                "SELECT s.sermon_guid, s.sermon_title, s.audiofilename, s.transcription, s.categories "
                "FROM sermons s "
                "WHERE s.transcription LIKE ? AND s.language = ? "
                f"{filter_clause} LIMIT 25"
            )
            params = [like_query, language] + filter_params
            cur = db.execute(fallback_sql, params)
            sermons = cur.fetchall()

        for sermon in sermons:
            snippets = extract_relevant_snippets(sermon["transcription"], query)
            if not snippets or snippets == ["(No exact match found)"]:
                snippets = [sermon["transcription"][:200]]  # Fallback snippet
            results.append({
                "sermon_guid": sermon["sermon_guid"],
                "sermon_title": sermon["sermon_title"],
                "audiofilename": sermon["audiofilename"],
                "categories": sermon["categories"],
                "snippets": snippets
            })

        app.logger.debug(f"Total results found: {len(results)}")

    except Exception as e:
        app.logger.error(f"Error during search: {str(e)}", exc_info=True)
        return render_template("error.html", message=_("An error occurred while processing your search. Please try again."))

    return render_template("results.html", 
                           query=query, 
                           results=results,
                           highlight_search_terms=highlight_search_terms,
                           all_categories=all_categories,
                           selected_categories=selected_categories)





@app.route("/sermon/<sermon_guid>")
def sermon_detail(sermon_guid):
    """Retrieve and display a sermon with the correct language version."""
    db = get_db()
    language = request.cookies.get("language", "en")  # Get user-selected language
    query = request.args.get("q", "").strip()
    selected_categories = request.args.getlist("categories")

    cur = db.execute(
        "SELECT * FROM sermons WHERE sermon_guid = ? AND language = ?",
        (sermon_guid, language),
    )
    sermon = cur.fetchone()

    # Fallback to English if the selected language version is unavailable
    if not sermon:
        cur = db.execute(
            "SELECT * FROM sermons WHERE sermon_guid = ? AND language = 'en'",
            (sermon_guid,),
        )
        sermon = cur.fetchone()

    if not sermon:
        return _("Sermon not found"), 404

    # Format and highlight transcription
    formatted_transcript = format_text_into_paragraphs(sermon["transcription"])
    highlighted_transcript = highlight_search_terms(formatted_transcript, query)

    return render_template(
        "sermon.html",
        sermon=sermon,
        formatted_transcript=highlighted_transcript,
        query=query,
        selected_categories=selected_categories
    )

@app.route("/stats")
def stats():
    return render_template("stats.html")


@app.route("/sermons")
def sermon_index():
    """Retrieve sermons and display the first 3-4 sentences of each transcription as a snippet."""
    db = get_db()
    language = request.cookies.get("language", "en")
    
    cur = db.execute("SELECT sermon_guid, sermon_title, audiofilename, transcription, categories FROM sermons WHERE language = ? ORDER BY sermon_title ASC", (language,))
    sermons = cur.fetchall()

    def extract_first_sentences(text, min_sentences=3, max_sentences=4):
        """Extracts the first few sentences from the transcription."""
        if not text:
            return "(No transcription available)"
        
        sentences = re.split(r'(?<=[.!?])\s+', text)  # Splits at sentence endings
        snippet = " ".join(sentences[:random.randint(min_sentences, max_sentences)])  # Get first 3-4 sentences
        return snippet

    # Process sermons and add snippets
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

    audio_filename = f"{sermon_guid}_{language}.mp3"
    audiofile.save(os.path.join("/data/audiofiles", audio_filename))

    try:
        with sqlite3.connect(DATABASE) as conn:
            cursor = conn.cursor()
            cursor.execute('''
                INSERT INTO sermons (sermon_title, transcription, audiofilename, sermon_guid, language, categories, church)
                VALUES (?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(sermon_guid, language) 
                DO UPDATE SET
                    sermon_title = excluded.sermon_title,
                    transcription = excluded.transcription,
                    audiofilename = excluded.audiofilename,
                    categories = excluded.categories,
                    church = excluded.church
            ''', (sermon_title, transcription, audio_filename, sermon_guid, language, categories, church))
            conn.commit()
    except sqlite3.IntegrityError:
        return jsonify({"error": "Database error occurred."}), 400

    return jsonify({"message": "Sermon uploaded successfully", "guid": sermon_guid}), 200

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000, debug=True)
