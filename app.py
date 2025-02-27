import os
import re
import random
import sqlite3
from flask import Flask, g, render_template, request, send_from_directory

app = Flask(__name__)
DATABASE = "sermons.db"

def get_db():
    """Connect to the SQLite database."""
    db = getattr(g, '_database', None)
    if db is None:
        db = g._database = sqlite3.connect(DATABASE)
        db.row_factory = sqlite3.Row
    return db

@app.teardown_appcontext
def close_connection(exception):
    """Close the database connection after each request."""
    db = getattr(g, '_database', None)
    if db is not None:
        db.close()


def extract_relevant_snippets(transcript, query, max_snippets=3):
    """Extract up to max_snippets sentences that contain the search term."""
    sentences = re.split(r'(?<=[.!?])\s+', transcript)  # Split transcript into sentences
    matched_sentences = [s for s in sentences if re.search(rf'\b{re.escape(query)}\b', s, re.IGNORECASE)]
    return matched_sentences[:max_snippets] if matched_sentences else ["(No exact match found)"]


def format_text_into_paragraphs(text, min_sentences=3, max_sentences=6):
    """Breaks long text into readable paragraphs by grouping sentences."""
    sentences = re.split(r'(?<=[.!?])\s+', text)  # Split on punctuation
    paragraphs = []
    i = 0

    while i < len(sentences):
        num_sentences = random.randint(min_sentences, max_sentences)  # Random para length
        paragraph = ' '.join(sentences[i:i + num_sentences])  # Combine sentences
        paragraphs.append(paragraph.strip())  # Remove any extra spaces
        i += num_sentences

    return ''.join(f"<p>{p}</p>" for p in paragraphs)  # Wrap each in <p> tags


def highlight_search_terms(text, query):
    """Wraps search terms in a highlight span tag."""
    if not query or query.strip() == "":
        return text  # No query provided, return text unchanged

    words = query.split()  # Split multi-word searches
    for word in words:
        regex = re.compile(rf'(\b{re.escape(word)}\b)', re.IGNORECASE)  # Match words exactly
        text = regex.sub(r'<span class="highlight">\1</span>', text)  # Apply highlight

    return text


@app.route("/")
def index():
    """Render the static homepage."""
    return render_template("index.html")


@app.route("/search", methods=["GET"])
def search():
    """Handles searching for sermons by keyword."""
    query = request.args.get("q", "").strip()

    # If no query is provided, show the search page instead of results
    if not query:
        return render_template("search.html")

    results = []
    db = get_db()
    cur = db.execute("SELECT id, title, mp3_file, transcript FROM sermons WHERE transcript LIKE ? LIMIT 25", (f"%{query}%",))
    sermons = cur.fetchall()

    for sermon in sermons:
        snippets = extract_relevant_snippets(sermon["transcript"], query)
        results.append({
            "id": sermon["id"],
            "title": sermon["title"],
            "mp3_file": sermon["mp3_file"],
            "snippets": [highlight_search_terms(s, query) for s in snippets]  # Highlight search term
        })

    return render_template("results.html", query=query, results=results)


@app.route("/sermon/<int:sermon_id>")
def sermon_detail(sermon_id):
    """Display a detailed page for a sermon with highlighted search terms."""
    db = get_db()
    cur = db.execute("SELECT title, mp3_file, transcript FROM sermons WHERE id = ?", (sermon_id,))
    sermon = cur.fetchone()

    if not sermon:
        return "Sermon not found", 404

    query = request.args.get("q", "").strip()  # Extract search query

    # 🔹 Format text into readable paragraphs
    formatted_transcript = format_text_into_paragraphs(sermon["transcript"])

    # 🔹 Highlight search terms in text
    highlighted_transcript = highlight_search_terms(formatted_transcript, query)

    return render_template("sermon.html", sermon=sermon, formatted_transcript=highlighted_transcript, query=query)


@app.route("/sermons")
def sermon_index():
    """Lists all available sermon MP3 files with snippets."""
    db = get_db()
    cur = db.execute("SELECT id, title, mp3_file, transcript FROM sermons ORDER BY title ASC")
    sermons = cur.fetchall()

    sermon_list = []
    for sermon in sermons:
        snippet = extract_relevant_snippets(sermon["transcript"], "", max_snippets=1)[0]  # First relevant sentence
        sermon_list.append({
            "id": sermon["id"],
            "title": sermon["title"],
            "mp3_file": sermon["mp3_file"],
            "snippet": snippet
        })

    return render_template("sermons.html", sermons=sermon_list)


@app.route("/audiofiles/<path:filename>")
def audiofiles(filename):
    """Serve audio files from the 'audiofiles' directory."""
    return send_from_directory("audiofiles", filename)

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000, debug=True)
