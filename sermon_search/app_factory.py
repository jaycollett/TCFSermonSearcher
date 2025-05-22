"""
Application factory module for TCF Sermon Searcher.

This module contains the functions to create and configure the Flask application.
"""

import os
import logging
import datetime
from flask import Flask, g, request, current_app
from flask_babel import Babel, gettext as _
from werkzeug.middleware.proxy_fix import ProxyFix

from config import get_config
from sermon_search.database.models import init_main_db
from sermon_search.database.init_metrics_db import init_metrics_db
from sermon_search import __version__, __release_date__


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

    # Determine the correct paths for templates and static files
    current_dir = os.path.dirname(os.path.abspath(__file__))
    if os.path.basename(current_dir) == 'sermon_search':
        # Development environment
        template_dir = os.path.join(current_dir, 'templates')
        static_dir = os.path.join(current_dir, 'static')
    else:
        # Docker environment (flattened structure)
        template_dir = os.path.join(current_dir, 'templates')
        static_dir = os.path.join(current_dir, 'static')
        
    app = Flask(__name__, 
                template_folder=template_dir,
                static_folder=static_dir)
    
    # Apply ProxyFix middleware to handle HAProxy layer
    app.wsgi_app = ProxyFix(app.wsgi_app, x_for=1, x_proto=1)
    
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
    # Determine the translations directory path
    current_dir = os.path.dirname(os.path.abspath(__file__))
    if os.path.basename(current_dir) == 'sermon_search':
        # Development environment - translations is one level up
        translations_path = os.path.join(
            os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
            'translations'
        )
    else:
        # Docker environment - translations is in the same directory
        translations_path = os.path.join(current_dir, 'translations')
    app.config['BABEL_TRANSLATION_DIRECTORIES'] = translations_path
    app.logger.info(f"Setting translations directory to: {translations_path}")
    
    # Initialize Babel with a locale selector
    babel = Babel(app, locale_selector=get_locale)
    babel.locale_selector_func = get_locale  # Explicitly attach get_locale
    app.babel = babel

    # Initialize the configuration-specific settings if available
    if hasattr(Config, 'init_app'):
        Config.init_app(app)
    
    # Initialize the database (and other extensions) within the app context
    with app.app_context():
        init_main_db()
        init_metrics_db()

    # Register blueprint
    from sermon_search.routes import bp as main_bp
    
    app.register_blueprint(main_bp)  # All routes

    # Teardown: close the database connections after each request
    @app.teardown_appcontext
    def close_connection(exception):
        """Close database connections at the end of each request."""
        # Close main database
        db = getattr(g, '_database', None)
        if db is not None:
            db.close()
            
        # Close metrics database
        metrics_db = getattr(g, '_metrics_db', None)
        if metrics_db is not None:
            metrics_db.close()

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

    # Context processor: inject the language and app version into templates
    @app.context_processor
    def inject_template_globals():
        """
        Inject global variables into all templates.
        
        Returns:
            dict: Dictionary with language information and app version
        """
        language = request.cookies.get('language', 'en')
        return dict(
            language=language,
            app_version=__version__,
            release_date=__release_date__
        )
        
    # Add security headers to every response
    @app.after_request
    def set_security_headers(response):
        """
        Add security headers to all responses
        """
        response.headers["X-Frame-Options"] = "SAMEORIGIN"
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["X-XSS-Protection"] = "1; mode=block"
        response.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"
        return response

    return app
