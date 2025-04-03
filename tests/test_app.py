import os
import pytest
from flask import Flask
from sermon_search.app_factory import create_app
from flask import request
from flask_babel import Babel, gettext as _


def test_app_creation():
    """Test that the app is created correctly."""
    # Test with dynamic config from environment
    config_name = os.environ.get('FLASK_ENV', 'testing')
    app = create_app(config_name)
    assert app is not None
    assert isinstance(app, Flask)


def test_app_config():
    """Test app configuration with different configs."""
    # Development config
    app = create_app('development')
    assert app.config['DEBUG'] is True
    assert app.config['DATABASE'].endswith('sermons.db')
    
    # Production config - mock env vars to avoid permission issues
    original_db_path = os.environ.get('PROD_DATABASE_PATH')
    original_audio_dir = os.environ.get('PROD_AUDIOFILES_DIR')
    
    try:
        # Set temporary paths for testing
        os.environ['PROD_DATABASE_PATH'] = './data/prod_sermons.db'
        os.environ['PROD_AUDIOFILES_DIR'] = './data/prod_audiofiles'
        
        app = create_app('production') 
        assert app.config['DEBUG'] is False
    finally:
        # Restore original environment
        if original_db_path:
            os.environ['PROD_DATABASE_PATH'] = original_db_path
        else:
            os.environ.pop('PROD_DATABASE_PATH', None)
            
        if original_audio_dir:
            os.environ['PROD_AUDIOFILES_DIR'] = original_audio_dir
        else:
            os.environ.pop('PROD_AUDIOFILES_DIR', None)
    
    # Testing env should use test config
    app = create_app('testing')
    assert 'TESTING' in app.config


def test_truncate_text_filter(app):
    """Test the truncate_text template filter."""
    with app.app_context():
        # Test short text (no truncation)
        short_text = "This is a short text."
        assert app.jinja_env.filters['truncate_text'](short_text) == short_text
        
        # Test long text (with truncation)
        long_text = "This is a very long text that should be truncated because it exceeds the maximum length allowed for the truncate_text filter. It should cut off at the last space before the maximum length and add ellipsis."
        truncated = app.jinja_env.filters['truncate_text'](long_text)
        assert len(truncated) <= 165  # Default max length
        assert truncated.endswith('...')
        
        # Test with custom max length
        custom_truncated = app.jinja_env.filters['truncate_text'](long_text, 50)
        assert len(custom_truncated) <= 52
        assert custom_truncated.endswith('...')
        
        # Test None input
        assert app.jinja_env.filters['truncate_text'](None) == ''


def test_get_locale(app):
    """Test the get_locale function."""
    with app.test_client() as client:
        # Default locale should be 'en'
        response = client.get('/')
        assert app.babel.locale_selector_func() == 'en'
        
        # Set language cookie
        client.set_cookie('language', 'es')
        response = client.get('/')
        assert app.babel.locale_selector_func() == 'es'


def test_inject_language(app):
    """Test that the language is injected into templates."""
    @app.route('/test-language')
    def test_language():
        from flask import render_template_string
        return render_template_string('{{ language }}')
    
    with app.test_client() as client:
        # Default language should be 'en'
        response = client.get('/test-language')
        assert response.data == b'en'
        
        # Set language cookie to 'es'
        client.set_cookie('language', 'es')
        response = client.get('/test-language')
        assert response.data == b'es'
