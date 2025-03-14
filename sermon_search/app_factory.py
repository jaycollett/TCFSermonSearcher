"""
Application factory module for TCF Sermon Searcher.

This module contains the functions to create and configure the Flask application.
"""

import os
import logging
from flask import Flask, g, request, current_app
from flask_babel import Babel, gettext as _

from config import get_config
from sermon_search.database.models import init_db


def get_locale():
    """
    Return the user's locale based on a cookie (default 'en').
    
    Returns:
        str: The locale code (e.g., 'en', 'es')
    """
    locale = request.cookies.get('language', 'en')
    if hasattr(current_app, 'logger') and current_app.logger:
        current_app.logger.debug(f"Using locale: {locale}, from cookie: {request.cookies}")
    return locale


def create_app(config_name=None):
    """
    Create and configure a Flask application instance.
    
    Args:
        config_name: Configuration to use ('development', 'testing', 'production') 
                    If None, uses FLASK_ENV environment variable
    
    Returns:
        Flask: Configured Flask application
    """
    if config_name is None:
        config_name = os.getenv('FLASK_ENV', 'development')

    app = Flask(__name__, 
                template_folder=os.path.join(os.path.dirname(os.path.abspath(__file__)), '../templates'),
                static_folder=os.path.join(os.path.dirname(os.path.abspath(__file__)), '../static'))
    
    # Get configuration based on environment
    Config = get_config(config_name)
    
    # Initialize directories if needed (only if not in testing mode)
    if hasattr(Config, 'init_directories') and not config_name == 'testing':
        Config.init_directories()
        
    app.config.from_object(Config)

    # Set up logging
    log_level = app.config.get('LOG_LEVEL', logging.INFO)
    logging.basicConfig(
        level=log_level,
        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
    )
    app.logger.setLevel(log_level)

    # Set Babel configuration
    app.config['BABEL_DEFAULT_LOCALE'] = 'en'
    app.config['BABEL_SUPPORTED_LOCALES'] = ['en', 'es']
    # Use absolute path to translations directory
    translations_path = os.path.join(
        os.path.dirname(os.path.dirname(os.path.abspath(__file__))), 
        'translations'
    )
    app.config['BABEL_TRANSLATION_DIRECTORIES'] = translations_path
    app.logger.info(f"Setting translations directory to: {translations_path}")
    
    # Initialize Babel with a locale selector
    babel = Babel(app, locale_selector=get_locale)
    babel.locale_selector_func = get_locale  # Explicitly attach get_locale
    app.babel = babel

    # Initialize the database (and other extensions) within the app context
    with app.app_context():
        init_db()

    # Register blueprints
    from sermon_search.routes import bp as main_bp
    from sermon_search.api import bp as api_bp
    
    app.register_blueprint(main_bp)  # Main UI routes
    app.register_blueprint(api_bp)   # API routes

    # Teardown: close the database connection after each request
    @app.teardown_appcontext
    def close_connection(exception):
        """Close database connection at the end of each request."""
        db = getattr(g, '_database', None)
        if db is not None:
            db.close()

    # Template filter: truncate text
    @app.template_filter('truncate_text')
    def truncate_text_filter(s, max_length=165):
        """
        Truncate text to a maximum length, cutting at word boundaries.
        
        Args:
            s: The string to truncate
            max_length: Maximum length before truncation
            
        Returns:
            str: Truncated string with ellipsis if needed
        """
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

    # Context processor: inject the language into templates
    @app.context_processor
    def inject_language():
        """
        Inject the current language into all templates.
        
        Returns:
            dict: Dictionary with language information
        """
        language = request.cookies.get('language', 'en')
        return dict(language=language)

    return app