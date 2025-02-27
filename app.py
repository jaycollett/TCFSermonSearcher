import sqlite3
from flask import Flask, g, render_template, request, send_from_directory, url_for

DATABASE = 'sermons.db'
app = Flask(__name__)

def get_db():
    db = getattr(g, '_database', None)
    if db is None:
        db = g._database = sqlite3.connect(DATABASE)
        # Return rows as dictionaries.
        db.row_factory = sqlite3.Row
    return db

@app.teardown_appcontext
def close_connection(exception):
    db = getattr(g, '_database', None)
    if db is not None:
        db.close()

@app.route('/')
def index():
    return render_template('index.html')

@app.route('/search')
def search():
    query = request.args.get('q', '')
    results = []
    if query:
        db = get_db()
        like_query = f"%{query}%"
        cur = db.execute("SELECT id, title, mp3_file, transcript FROM sermons WHERE transcript LIKE ? LIMIT 25", (like_query,))
        results = cur.fetchall()
    return render_template('results.html', query=query, results=results)

@app.route('/audiofiles/<path:filename>')
def audiofiles(filename):
    # Serve MP3 files from the "audiofiles" folder.
    return send_from_directory('audiofiles', filename)

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000, debug=True)

