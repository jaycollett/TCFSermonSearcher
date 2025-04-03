# config/default.py
import logging

class DefaultConfig:
    DEBUG = True

    BABEL_DEFAULT_LOCALE = 'en'
    BABEL_SUPPORTED_LOCALES = ['en', 'es']
    BABEL_TRANSLATION_DIRECTORIES = 'translations'
    
    # Shared images directory is None by default, will be set in production config
    SHARED_IMAGES_DIR = None

    # Configure logging
    logging.basicConfig(level=logging.DEBUG)
