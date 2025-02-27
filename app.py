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


def extract_relevant_snippets(transcript, query, max_snippets=3, context_words=8):
    """
    Extract snippets of text surrounding the search query.
    
    - `max_snippets`: Maximum number of snippets to return.
    - `context_words`: Number of words before and after the search term for context.
    """
    words = transcript.split()  # Tokenize transcript into words
    query_lower = query.lower()
    matched_snippets = []
    
    for i, word in enumerate(words):
        if query_lower in word.lower():
            start = max(0, i - context_words)
            end = min(len(words), i + context_words + 1)
            snippet = " ".join(words[start:end])
            matched_snippets.append(snippet)

            # Stop if we have enough snippets
            if len(matched_snippets) >= max_snippets:
                break
    
    return matched_snippets if matched_snippets else ["(No exact match found)"]



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
    """Wrap search terms in a highlight span tag with full case-insensitive matching."""
    if not query or query.strip() == "":
        return text  # No query provided, return text unchanged

    words = query.split()  # Split multi-word searches
    for word in words:
        regex = re.compile(rf'\b({re.escape(word)})\b', re.IGNORECASE)  # Match whole words only
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

    if not query:
        return render_template("search.html")

    results = []
    db = get_db()
    cur = db.execute("SELECT id, title, mp3_file, transcript FROM sermons WHERE transcript LIKE ? LIMIT 25", (f"%{query}%",))
    sermons = cur.fetchall()

    for sermon in sermons:
        snippets = extract_relevant_snippets(sermon["transcript"], query)

        # Ensure only relevant snippets are shown
        if snippets and snippets[0] != "(No exact match found)":
            highlighted_snippets = [highlight_search_terms(snippet, query) for snippet in snippets]  # Apply highlighting

            results.append({
                "id": sermon["id"],
                "title": sermon["title"],
                "mp3_file": sermon["mp3_file"],
                "snippets": highlighted_snippets  # Store highlighted snippets
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
