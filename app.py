import os
import logging
import sqlite3
import json
import datetime
import nltk
import math
nltk.download('stopwords', quiet=True)  # Consider checking if already downloaded
from nltk.corpus import stopwords
from flask import Flask, g, request
from flask_babel import Babel, gettext as _
from config import get_config
from models import init_db  # Database initialization function

def get_locale():
    """Return the user's locale based on a cookie (default 'en')."""
    return request.cookies.get('language', 'en')

def create_app(config_name=None):
    if config_name is None:
        config_name = os.getenv('FLASK_ENV', 'development')

    app = Flask(__name__)
    Config = get_config(config_name)
    app.config.from_object(Config)

    # Initialize Babel with a locale selector.
    babel = Babel(app, locale_selector=get_locale)

    # Initialize the database (and other extensions) within the app context.
    with app.app_context():
        init_db()

    # Register the blueprint from routes.py.
    from routes import bp as main_bp
    app.register_blueprint(main_bp)

    # Teardown: close the database connection after each request.
    @app.teardown_appcontext
    def close_connection(exception):
        db = getattr(g, '_database', None)
        if db is not None:
            db.close()

    # Template filter: truncate text.
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

    # Context processor: inject the language into templates.
    @app.context_processor
    def inject_language():
        language = request.cookies.get('language', 'en')
        return dict(language=language)

    return app

if __name__ == "__main__":
    app = create_app()
    # For production, consider using a WSGI server like gunicorn instead of app.run().
    app.run(host="0.0.0.0", port=5000, debug=True)
