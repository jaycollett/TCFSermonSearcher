import os
import re
import logging
import random
import sqlite3
from flask import Flask, g, render_template, request, send_from_directory

app = Flask(__name__)
DATABASE = "sermons.db"

# Configure logging
logging.basicConfig(level=logging.DEBUG)

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
    """Extract snippets of text surrounding the search query."""
    matched_snippets = []
    
    # Use regular expression to find the exact phrase in the transcript
    matches = re.finditer(re.escape(query), transcript)
    
    for match in matches:
        start = max(0, match.start() - context_words * 5) #Multiply context words to get character context.
        end = min(len(transcript), match.end() + context_words * 5)
        snippet = transcript[start:end]
        matched_snippets.append(snippet)
        
        if len(matched_snippets) >= max_snippets:
            break
    
    return matched_snippets if matched_snippets else ["(No exact match found)"]

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
    """Wraps search terms in a highlight span tag."""
    if not query or query.strip() == "":
        return text

    regex = re.compile(rf'({re.escape(query)})', re.IGNORECASE)
    text = regex.sub(r'<span class="highlight">\1</span>', text)

    return text

@app.route("/")
def index():
    """Render the static homepage."""
    return render_template("index.html")

@app.route("/search", methods=["GET"])
def search():
    """Handles searching for sermons using Full-Text Search (FTS5), supporting multi-word queries."""
    query = request.args.get("q", "").strip()

    if not query:
        return render_template("search.html")

    app.logger.info(f"Search query received: {query}")
    results = []

    try:
        db = get_db()
        cur = db.execute("SELECT id, title, mp3_file, transcript FROM sermons_fts WHERE sermons_fts MATCH ? LIMIT 25", (query,))
        sermons = cur.fetchall()

        for sermon in sermons:
            snippets = extract_relevant_snippets(sermon["transcript"], query)

            if snippets and snippets[0] != "(No exact match found)":
                highlighted_snippets = [highlight_search_terms(snippet, query) for snippet in snippets]

                results.append({
                    "id": sermon["id"],
                    "title": sermon["title"],
                    "mp3_file": sermon["mp3_file"],
                    "snippets": highlighted_snippets
                })

        app.logger.debug(f"Total results found: {len(results)}")

    except Exception as e:
        app.logger.error(f"Error during search: {str(e)}", exc_info=True)
        return render_template("error.html", message="An error occurred while processing your search. Please try again.")

    return render_template("results.html", query=query, results=results)

@app.route("/sermon/<int:sermon_id>")
def sermon_detail(sermon_id):
    """Display a detailed page for a sermon with highlighted search terms."""
    db = get_db()
    cur = db.execute("SELECT title, mp3_file, transcript FROM sermons WHERE id = ?", (sermon_id,))
    sermon = cur.fetchone()

    if not sermon:
        return "Sermon not found", 404

    query = request.args.get("q", "").strip()

    formatted_transcript = format_text_into_paragraphs(sermon["transcript"])
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
        snippet = extract_relevant_snippets(sermon["transcript"], "", max_snippets=1)[0]
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