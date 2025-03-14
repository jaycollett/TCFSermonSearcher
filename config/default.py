# config/default.py
import os
import logging

class DefaultConfig:
    DEBUG = True

    DATABASE = "/data/sermons.db"
    AUDIOFILES_DIR = "/data/audiofiles"

    BABEL_DEFAULT_LOCALE = 'en'
    BABEL_SUPPORTED_LOCALES = ['en', 'es']
    BABEL_TRANSLATION_DIRECTORIES = 'translations'

    # Ensure data directories exist
    os.makedirs(os.path.dirname(DATABASE), exist_ok=True)
    os.makedirs(AUDIOFILES_DIR, exist_ok=True)

    # Configure logging
    logging.basicConfig(level=logging.DEBUG)
