import os
import re
import logging
import random
import sqlite3
import uuid
import json
import datetime
import nltk
nltk.download('stopwords', quiet=True)
from nltk.corpus import stopwords
from flask import Flask, g, render_template, request, send_from_directory, redirect, url_for, make_response, jsonify
from flask_babel import Babel, gettext as _
from collections import Counter
# For generating the bar chart without a display (headless)
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from wordcloud import WordCloud, STOPWORDS

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


    """
    Check if a column exists in the table.
    If not, alter the table to add the column using the given definition.
    """
    cursor = conn.execute(f"PRAGMA table_info({table})")
    columns = [row["name"] for row in cursor.fetchall()]
    if column not in columns:
        conn.execute(f"ALTER TABLE {table} ADD COLUMN {column} {column_def}")
        conn.commit()
        app.logger.info(f"Added missing column '{column}' to '{table}'.")

def drop_column_if_exists(conn, table, column):
    """
    Drops a column from the table if it exists.
    Note: Requires SQLite 3.35.0 or later.
    """
    cursor = conn.execute(f"PRAGMA table_info({table})")
    columns = [row["name"] for row in cursor.fetchall()]
    if column in columns:
        try:
            conn.execute(f"ALTER TABLE {table} DROP COLUMN {column}")
            conn.commit()
            app.logger.info(f"Dropped column '{column}' from table '{table}'.")
        except sqlite3.Error as e:
            app.logger.error(f"Error dropping column '{column}' from table '{table}': {e}")

def init_db():
    """Ensure the database exists and initialize tables."""
    app.logger.info("Initializing database...")

    if not os.path.exists(DATABASE):
        app.logger.info(f"Database file '{DATABASE}' does not exist. Creating it.")
        open(DATABASE, 'w').close()

    with sqlite3.connect(DATABASE) as conn:
        conn.row_factory = sqlite3.Row
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
                    insert_date DATETIME DEFAULT CURRENT_TIMESTAMP,
                    church NVARCHAR(10),
                    UNIQUE (sermon_guid, language)
                )
            ''')
            conn.commit()

            # Drop the unwanted columns if they exist.
            drop_column_if_exists(conn, "sermons", "ai_summary")
            drop_column_if_exists(conn, "sermons", "ai_identified_books")

            cursor.execute('CREATE INDEX IF NOT EXISTS idx_sermon_guid ON sermons (sermon_guid)')
            cursor.execute('CREATE INDEX IF NOT EXISTS idx_sermons_language ON sermons(language);')
            cursor.execute('CREATE INDEX IF NOT EXISTS idx_sermons_categories ON sermons(categories);')
            cursor.execute('CREATE INDEX IF NOT EXISTS idx_sermons_ai_identified_books ON sermons(ai_identified_books);')
            conn.commit()


            app.logger.info("Sermons table created successfully.")
        except sqlite3.Error as e:
            app.logger.error(f"Error creating sermons table: {e}")

        try:
            app.logger.info("Creating stats_for_nerds table...")
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS stats_for_nerds (
                    id INTEGER PRIMARY KEY,
                    total_sermons INTEGER,
                    average_words_per_sermon INTEGER,
                    largest_sermon_title TEXT,
                    largest_sermon_word_count INTEGER,
                    shortest_sermon_title TEXT,
                    shortest_sermon_word_count INTEGER,
                    top_ten_words TEXT,
                    most_common_category TEXT,
                    updated_at DATETIME DEFAULT CURRENT_TIMESTAMP
                )
            ''')
            conn.commit()
            app.logger.info("stats_for_nerds table created successfully.")
        except sqlite3.Error as e:
            app.logger.error(f"Error creating stats_for_nerds table: {e}")

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
                app.logger.info("Creating ai_sermon_content table...")
                cursor.execute('''
                    CREATE TABLE IF NOT EXISTS ai_sermon_content (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        sermon_guid VARCHAR(40) NOT NULL,
                        ai_summary TEXT,
                        ai_summary_es TEXT,
                        bible_books TEXT,
                        bible_books_es TEXT,
                        created_at DATETIME,
                        key_quotes TEXT,
                        key_quotes_es TEXT,
                        sentiment TEXT,
                        sentiment_es TEXT,
                        sermon_style TEXT,
                        sermon_style_es TEXT,
                        status VARCHAR(50),
                        topics TEXT,
                        topics_es TEXT,
                        updated_at DATETIME,
                        FOREIGN KEY (sermon_guid) REFERENCES sermons(sermon_guid)
                    )
                ''')
                conn.commit()
                app.logger.info("ai_sermon_content table created successfully.")
        except sqlite3.Error as e:
            app.logger.error(f"Error creating ai_sermon_content table: {e}")

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
    """Retrieve and display a sermon along with AI-generated content based on the correct language version."""
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

    # Fetch AI-generated sermon content
    cur = db.execute(
        "SELECT * FROM ai_sermon_content WHERE sermon_guid = ?",
        (sermon_guid,)
    )
    ai_content = cur.fetchone()

    # Format and highlight transcription
    formatted_transcript = format_text_into_paragraphs(sermon["transcription"])
    highlighted_transcript = highlight_search_terms(formatted_transcript, query)

    return render_template(
        "sermon.html",
        sermon=sermon,
        ai_content=ai_content,  # Pass AI-generated content
        language=language,
        formatted_transcript=highlighted_transcript,
        query=query,
        selected_categories=selected_categories
    )


@app.route("/stats")
@app.route("/stats")
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
        # If no stats record exists, use numeric defaults so the round filter works.
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

#
#
# API ENDPOINTS
#
#

@app.route("/api/update_stats", methods=["POST"])
def update_stats():

    #
    #
    # TODO: We should make the sermon title on the stats for nerds a link to the sermon.
    #

    # Validate IP ban and API token (similar to upload_sermon)
    ip = get_client_ip()  # Get actual client IP
    db = get_db()
    
    if is_ip_banned(ip):
        return jsonify({"error": "Too many failed attempts. Try again later."}), 403

    api_token = request.headers.get("X-API-Token")
    if not api_token or api_token != os.environ.get("SERMON_API_TOKEN", ""):
        cur = db.execute("SELECT failed_attempts FROM ip_bans WHERE ip_address = ?", (ip,))
        row = cur.fetchone()
        attempts = row["failed_attempts"] + 1 if row else 1
        if attempts >= 3:
            banned_until = int(datetime.datetime.utcnow().timestamp()) + 86400  # 24 hours from now
            db.execute("REPLACE INTO ip_bans (ip_address, failed_attempts, banned_until) VALUES (?, ?, ?)", 
                       (ip, attempts, banned_until))
        else:
            db.execute("REPLACE INTO ip_bans (ip_address, failed_attempts, banned_until) VALUES (?, ?, NULL)", 
                       (ip, attempts))
        db.commit()
        return jsonify({"error": "Unauthorized"}), 401

    # Retrieve all sermons
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

    # Find the sermon with the most and fewest words
    largest_sermon = max(sermon_stats, key=lambda x: x["word_count"])
    shortest_sermon = min(sermon_stats, key=lambda x: x["word_count"])

    # Compute the top ten most used words across all sermons using NLTK stopwords.
    all_text = " ".join([sermon["transcription"] for sermon in sermons])
    all_text_clean = re.sub(r'[^\w\s]', '', all_text.lower())
    words = all_text_clean.split()
    stop_words = set(stopwords.words('english'))
    filtered_words = [w for w in words if w not in stop_words]
    counter = Counter(filtered_words)
    top_ten_list = [{"word": word, "count": count} for word, count in counter.most_common(10)]
    top_ten_words = json.dumps(top_ten_list)

    # Build a word cloud image from the full transcription text.
    static_images_dir = os.path.join(app.root_path, "static", "images")
    if not os.path.exists(static_images_dir):
        os.makedirs(static_images_dir)
    word_cloud_path = os.path.join(static_images_dir, "data_cloud.png")
    combined_stopwords = STOPWORDS.union(stop_words)
    wc = WordCloud(width=800, height=400, background_color="white", stopwords=combined_stopwords).generate(all_text)
    wc.to_file(word_cloud_path)

    # Compute top ten bi-grams from the filtered words.
    bigrams = zip(filtered_words, filtered_words[1:])
    bigram_list = [' '.join(bigram) for bigram in bigrams]
    bigram_counter = Counter(bigram_list)
    top_ten_bigrams = bigram_counter.most_common(10)

    # Generate a bar chart for the top 10 bi-grams.
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

    # Compute the most common category from sermons' categories.
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

    # Update the stats_for_nerds table: Delete any previous record and insert new stats.
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

@app.route("/api/ai_sermon_content", methods=["POST"])
def upload_ai_sermon_content():
    # Optional: Validate the API token similar to your other endpoints.
    api_token = request.headers.get("X-API-Token")
    if not api_token or api_token != os.environ.get("SERMON_API_TOKEN", ""):
        return jsonify({"error": "Unauthorized"}), 401

    data = request.get_json()
    if not data:
        return jsonify({"error": "Invalid JSON payload"}), 400

    # List of required fields based on your JSON structure.
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

    # Validate that all required fields are present.
    for field in required_fields:
        if field not in data or data[field] is None:
            return jsonify({"error": f"Missing field: {field}"}), 400

    # Validate that sermon_guid is a valid UUID.
    try:
        uuid.UUID(data["sermon_guid"])
    except ValueError:
        return jsonify({"error": "Invalid sermon_guid format. Must be a valid UUID."}), 400

    # Validate datetime fields: expecting the format YYYY-MM-DD HH:MM:SS.
    for dt_field in ["created_at", "updated_at"]:
        try:
            datetime.datetime.strptime(data[dt_field], "%Y-%m-%d %H:%M:%S")
        except ValueError:
            return jsonify({"error": f"Invalid datetime format for {dt_field}. Expected YYYY-MM-DD HH:MM:SS"}), 400

    # Insert the validated data into the ai_sermon_content table.
    db = get_db()
    try:
        cursor = db.cursor()
        cursor.execute('''
            INSERT INTO ai_sermon_content (
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
        app.logger.error(f"Database error: {e}")
        return jsonify({"error": "Database error occurred."}), 500

    return jsonify({"message": "ok"}), 200


@app.route("/upload_sermon", methods=["POST"])  # for backwards compatibility until the orchestrator is updated.
@app.route("/api/upload_sermon", methods=["POST"])
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


#
#
# Main Init
#
#

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000, debug=True)
